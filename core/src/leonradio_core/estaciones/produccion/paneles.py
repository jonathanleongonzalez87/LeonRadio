"""Paneles de Producción: «Comercial» (clientes, contratos y pauta)."""

from __future__ import annotations

from datetime import date

from ... import sdk
from ...entities import norm
from ...uischema import UI
from . import comercial as C

POR_PAGINA = 50
PESTANAS = (("cliente", "Clientes"), ("contrato", "Contratos"), ("compromiso", "Pauta"))
NUEVO = {"cliente": "Nuevo cliente", "contrato": "Nuevo contrato", "compromiso": "Nueva pauta"}
CONTEO = {"cliente": ("cliente", "clientes"), "contrato": ("contrato", "contratos"), "compromiso": ("pauta", "pautas")}
SIN_ARCHIVADOS = {"cliente": "No hay clientes archivados.", "contrato": "No hay contratos archivados.",
                  "compromiso": "No hay pautas archivadas."}
NOTA_FRANJA = "Si la franja cruza la medianoche (de 22:00 a 02:00) también vale. Si la dejas vacía, cuenta todo el día."


def _pesos(v) -> str:
    return "—" if v is None else "$ " + f"{v:,}".replace(",", ".")


def _texto(v) -> str:
    return "—" if v is None or v == "" else str(v)


def _estado_contrato(c: dict, hoy: date) -> str:
    if date.fromisoformat(c["desde"]) > hoy:
        return "por empezar"
    return "terminado" if date.fromisoformat(c["hasta"]) < hoy else "vigente"


def _leer(ctx: sdk.Context) -> dict:
    ents = ctx.entities
    spots = ents.list("pieza", where={"kind": "spot"}, limit=200)
    return {"cliente": C.todas(ents, "cliente", include_archived=True),
            "contrato": C.todas(ents, "contrato", include_archived=True),
            "compromiso": C.todas(ents, "compromiso", include_archived=True),
            "spots": spots["items"], "spots_total": spots["total"]}


class ComercialPanel(sdk.Editor):
    id, label, icon = "produccion.comercial", "Comercial", "▥"
    station = "produccion"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        ui.label("Comercial", "title")
        ui.label("Aquí registras a quién le vendes, qué le vendiste y qué debe sonar al aire. "
                 "Programación usa estos datos para armar las tandas.", "muted")
        try:
            d = _leer(ctx)
        except Exception:  # noqa: BLE001 - nunca el texto técnico en pantalla
            sdk.log.exception("Producción: no se pudo leer la lista comercial")
            ui.label("No se pudo cargar la lista. Vuelve a intentarlo; si sigue igual, avisa a quien administra la "
                     "plataforma.", "warn")
            ui.button("Reintentar", "produccion.cerrar")
            return
        tz = C.zona(ctx.config)
        d["hoy"], d["tz"] = C.hoy(tz), tz
        d["por_id"] = {e: {r["id"]: r for r in d[e]} for e in ("cliente", "contrato")}
        d["titulos"] = {s["id"]: s["title"] for s in d["spots"]}
        with ui.tabs("produccion.comercial") as t:
            for entidad, nombre in PESTANAS:
                with t.tab(nombre):
                    self._pestana(ui, ctx, d, entidad)

    # -- una pestaña: aviso, botones, edición, tabla y conteo ---------------------------------------------------------
    def _pestana(self, ui: UI, ctx: sdk.Context, d: dict, e: str) -> None:
        st = ctx.state
        if st.get("produccion.aviso_de") in (e, None):     # sin entidad: aviso de un comando sin registro abierto
            if st.get("produccion.aviso"):
                ui.label(st["produccion.aviso"], "warn")
            if st.get("produccion.listo"):
                ui.label(st["produccion.listo"], "ok")
        archivados = bool((st.get("produccion.archivados") or {}).get(e))
        activos_cli = [r for r in d["cliente"] if not r["archived"]]
        activos_con = [r for r in d["contrato"] if not r["archived"]]
        falta = None                                   # lo que hay que crear antes (estado vacío sin botón «Nuevo»)
        if e == "contrato" and not activos_cli:
            falta = ("Primero crea un cliente en la pestaña «Clientes».", "normal")
        elif e == "compromiso" and not activos_con:
            falta = ("Primero crea un contrato en la pestaña «Contratos».", "normal")
        elif e == "compromiso" and not d["spots"]:
            falta = ("No hay cuñas en la biblioteca. Las cuñas se toman de la carpeta «Spots».", "warn")
        with ui.row():
            if not archivados and not falta:
                ui.button(NUEVO[e], "produccion.ver", {"entidad": e})
            ui.button("Activos", "produccion.archivados", {"entidad": e, "ver": False}, size="sm", selected=not archivados)
            ui.button("Archivados", "produccion.archivados", {"entidad": e, "ver": True}, size="sm", selected=archivados)
        sel = st.get("produccion.sel")
        if sel and sel.get("entidad") == e:
            self._seleccion(ui, ctx, d, e, sel)
        filas = [r for r in d[e] if bool(r["archived"]) == archivados]
        if not filas:
            if archivados:
                ui.label(SIN_ARCHIVADOS[e], "muted")
            elif falta:
                ui.label(*falta)
            else:
                vacio = {"cliente": ("Aún no hay clientes.", "Crea el primero para poder registrar sus contratos."),
                         "contrato": ("Aún no hay contratos.", "Crea el primero con «Nuevo contrato»."),
                         "compromiso": ("Aún no hay pautas.",
                                        "Registra qué cuña debe sonar, cuántas veces y entre qué fechas.")}[e]
                ui.label(vacio[0])
                ui.label(vacio[1], "muted")
            n = len(d[e])
            if not archivados and n:
                fem = "a" if e == "compromiso" else "o"
                ui.label(f"Hay {n} archivad{fem}{'s' if n != 1 else ''}; míral{fem}{'s' if n != 1 else ''} en «Archivados».",
                         "muted")
            return
        if e == "cliente":
            filas.sort(key=lambda r: (norm(r["nombre"]), r["id"]))
        elif e == "contrato":
            filas.sort(key=lambda r: (r["desde"], r["id"]), reverse=True)
        else:
            filas.sort(key=lambda r: (C.local(r["window_start"], d["tz"]), r["id"]), reverse=True)
        total = len(filas)
        offset = int((st.get("produccion.offset") or {}).get(e, 0))
        if offset >= total:
            offset = max(0, (total - 1) // POR_PAGINA * POR_PAGINA)
        pagina = filas[offset:offset + POR_PAGINA]
        getattr(self, f"_tabla_{e}")(ui, ctx, d, pagina, archivados)
        uno, varios = CONTEO[e]
        if total > POR_PAGINA:
            ui.label(f"{offset + 1}–{offset + len(pagina)} de {total}", "muted")
            with ui.row():
                if offset > 0:
                    ui.button("Anteriores", "produccion.pagina", {"entidad": e, "offset": max(0, offset - POR_PAGINA)},
                              size="sm")
                if offset + POR_PAGINA < total:
                    ui.button("Siguientes", "produccion.pagina", {"entidad": e, "offset": offset + POR_PAGINA}, size="sm")
        else:
            ui.label(f"{total} {uno if total == 1 else varios}", "muted")

    @staticmethod
    def _acciones(e: str, r: dict, archivados: bool, bloqueo: str | None = None):
        if archivados:
            return bloqueo or UI.actions(("Restaurar", f"{e}.restaurar", {"id": r["id"]}))
        return UI.actions(("Editar", "produccion.ver", {"entidad": e, "id": r["id"]}),
                          ("Archivar", "produccion.ver", {"entidad": e, "id": r["id"], "archivar": True}))

    def _tabla_cliente(self, ui, ctx, d, filas, archivados) -> None:
        vigentes: dict[int, int] = {}
        for c in d["contrato"]:
            if not c["archived"] and _estado_contrato(c, d["hoy"]) == "vigente":
                vigentes[c["cliente_id"]] = vigentes.get(c["cliente_id"], 0) + 1
        ui.table(["Nombre", "Contratos vigentes", "Acciones"],
                 [[r["nombre"], vigentes.get(r["id"], 0), self._acciones("cliente", r, archivados)] for r in filas])

    def _tabla_contrato(self, ui, ctx, d, filas, archivados) -> None:
        rows = []
        for r in filas:
            cli = d["por_id"]["cliente"].get(r["cliente_id"])
            bloqueo = "Restaura primero su cliente" if cli is None or cli["archived"] else None
            rows.append([r["codigo"], cli["nombre"] if cli else "—", r["tipo"].capitalize(),
                         f"{C.fecha_corta(r['desde'])} – {C.fecha_corta(r['hasta'])}", _pesos(r["valor_cop"]),
                         "archivado" if r["archived"] else _estado_contrato(r, d["hoy"]), self._acciones("contrato", r, archivados, bloqueo)])
        ui.table(["Código", "Cliente", "Tipo", "Vigencia", "Valor", "Estado", "Acciones"], rows, narrow_hide=[2, 3])

    @staticmethod
    def _titulo_real(ctx, d, asset_id) -> str | None:
        """Título de la pieza aunque esté retirada (formulario); `None` si ya no existe."""
        reales = d.setdefault("reales", {})
        if asset_id not in reales:
            try:
                reales[asset_id] = ctx.entities.get("pieza", asset_id)["title"]
            except ValueError:
                reales[asset_id] = None
        return reales[asset_id]

    def _titulo_cuna(self, ctx, d, asset_id) -> str:
        if asset_id is None:
            return "—"
        if asset_id not in d["titulos"]:
            try:
                p = ctx.entities.get("pieza", asset_id)
                d["titulos"][asset_id] = p["title"] if p["status"] == "active" and p["kind"] == "spot" else None
            except ValueError:
                d["titulos"][asset_id] = None
        return d["titulos"][asset_id] or "(cuña no disponible)"

    def _tabla_compromiso(self, ui, ctx, d, filas, archivados) -> None:
        rows = []
        for r in filas:
            con = d["por_id"]["contrato"].get(r["contrato_id"]) if r["contrato_id"] else None
            if con:
                cli = d["por_id"]["cliente"].get(con["cliente_id"])
                contrato, cliente = con["codigo"], cli["nombre"] if cli else "—"
            else:
                contrato, cliente = "(sin contrato)", _texto(r["client"])
            bloqueo = "Restaura primero su contrato" if con is not None and con["archived"] else None
            franja = (f"{r['daypart_start']} – {r['daypart_end']}" if r["daypart_start"] and r["daypart_end"]
                      else "Todo el día")
            vigencia = (f"{C.fecha_corta(C.dia_inicio(r['window_start'], d['tz']))} – "
                        f"{C.fecha_corta(C.dia_final(r['window_end'], d['tz']))}")
            rows.append([contrato, cliente, self._titulo_cuna(ctx, d, r["asset_id"]), _texto(r["campaign"]),
                         r["plays_required"], vigencia, franja, self._acciones("compromiso", r, archivados, bloqueo)])
        ui.table(["Contrato", "Cliente", "Cuña", "Campaña", "Cantidad", "Vigencia", "Franja", "Acciones"], rows,
                 narrow_hide=[3, 5, 6])

    # -- bloque superior: edición, borrador o confirmación de archivar --------------------------------------------------
    def _seleccion(self, ui: UI, ctx: sdk.Context, d: dict, e: str, sel: dict) -> None:
        fila = None
        if sel.get("id") is not None:
            fila = next((r for r in d[e] if r["id"] == sel["id"]), None)
            if fila is None:
                return
        if sel.get("archivar"):
            self._confirmar(ui, d, e, fila)
            return
        borrador = sel.get("borrador") if fila is None else None
        if fila is None:
            ui.label(NUEVO[e], "title")
        elif e == "cliente":
            ui.label(fila["nombre"], "title")
        elif e == "contrato":
            ui.label(f"Contrato {fila['codigo']}", "title")
        else:
            titulo = self._titulo_real(ctx, d, fila["asset_id"]) if fila["asset_id"] else None
            ui.label(f"Pauta de «{titulo}»" if titulo else "Pauta", "title")
        valores = ({k: x if isinstance(x, str) else "" for k, x in borrador.items()} if borrador is not None
                   else self._valores(ctx, d, e, fila, sel.get("pendiente") or {}))
        ui.form("produccion.campo", getattr(self, f"_campos_{e}")(d, valores))
        if e == "compromiso":
            ui.label(NOTA_FRANJA, "muted")
            if d["spots_total"] > len(d["spots"]):
                ui.label(f"Se muestran las primeras {len(d['spots'])} cuñas.", "muted")
        ui.label("Rellena los campos y pulsa «Guardar»." if borrador is not None
                 else "Los cambios se guardan al salir de cada campo.", "muted")
        with ui.row():
            if borrador is not None:
                ui.button("Guardar", "produccion.guardar")
                ui.button("Cancelar", "produccion.cerrar")
            else:
                ui.button("Cerrar", "produccion.cerrar")

    def _confirmar(self, ui: UI, d: dict, e: str, fila: dict) -> None:
        if e == "cliente":
            n = sum(1 for c in d["contrato"] if not c["archived"] and c["cliente_id"] == fila["id"])
            titulo, bloqueo = f"¿Archivar a «{fila['nombre']}»?", (
                f"«{fila['nombre']}» tiene {n} contrato{'s' if n != 1 else ''} activo{'s' if n != 1 else ''}. "
                f"Archívalo{'s' if n != 1 else ''} primero.")
        elif e == "contrato":
            n = sum(1 for c in d["compromiso"] if not c["archived"] and c["contrato_id"] == fila["id"])
            titulo, bloqueo = f"¿Archivar el contrato {fila['codigo']}?", (
                f"El contrato {fila['codigo']} tiene {n} pauta{'s' if n != 1 else ''} activa{'s' if n != 1 else ''}. "
                f"Archíva{'las' if n != 1 else 'la'} primero.")
        else:
            n, titulo, bloqueo = 0, "¿Archivar esta pauta?", ""
        if n:
            ui.label("No se puede archivar todavía", "title")
            ui.label(bloqueo, "warn")
            ui.button("Entendido", "produccion.cerrar")
            return
        ui.label(titulo, "title")
        suf = "la" if e == "compromiso" else "lo"
        ui.label(f"Dejará de aparecer en las listas y en los formularios. No se borra nada: puedes restaurar{suf} "
                 f"desde «Archivados».")
        with ui.row():
            ui.button("Archivar", f"{e}.archivar", {"id": fila["id"]})
            ui.button("Cancelar", "produccion.cerrar")

    # -- formularios ------------------------------------------------------------------------------------------------------
    def _valores(self, ctx: sdk.Context, d: dict, e: str, fila: dict, pendiente: dict) -> dict:
        """Fila guardada → lo que muestra el formulario (nombres en vez de ids, DD/MM/AAAA, $ con puntos)."""
        if e == "cliente":
            return {"nombre": fila["nombre"], "notas": fila["notas"] or ""}
        if e == "contrato":
            cli = d["por_id"]["cliente"].get(fila["cliente_id"])
            return {"codigo": fila["codigo"], "cliente_id": cli["nombre"] if cli else "", "tipo": fila["tipo"].capitalize(),
                    "desde": C.fecha_corta(fila["desde"]), "hasta": C.fecha_corta(fila["hasta"]),
                    "valor_cop": "" if fila["valor_cop"] is None else f"{fila['valor_cop']:,}".replace(",", "."),
                    "descripcion": fila["descripcion"] or ""}
        con = d["por_id"]["contrato"].get(fila["contrato_id"]) if fila["contrato_id"] else None
        out = {"contrato_id": self._opcion_contrato(d, con) if con else "",
               "asset_id": self._opcion_cuna(ctx, d, fila["asset_id"]) if fila["asset_id"] else "",
               "campana": fila["campaign"] or "", "cantidad": fila["plays_required"],
               "desde": C.fecha_corta(C.dia_inicio(fila["window_start"], d["tz"])),
               "hasta": C.fecha_corta(C.dia_final(fila["window_end"], d["tz"])),
               "franja_desde": fila["daypart_start"] or "", "franja_hasta": fila["daypart_end"] or "",
               "notas": fila["notes"] or ""}
        out.update({k: v for k, v in pendiente.items() if k in out})
        return out

    @staticmethod
    def _opcion_contrato(d: dict, con: dict) -> str:
        cli = d["por_id"]["cliente"].get(con["cliente_id"])
        return f"{con['codigo']} · {cli['nombre'] if cli else '—'}"

    def _opcion_cuna(self, ctx: sdk.Context, d: dict, asset_id: int) -> str:
        if d["titulos"].get(asset_id):
            return f"{asset_id} · {d['titulos'][asset_id]}"
        titulo = self._titulo_real(ctx, d, asset_id)
        return f"{asset_id} · {titulo} (no disponible)" if titulo else f"{asset_id} · (cuña no disponible)"

    @staticmethod
    def _con_valor(opciones: list[str], valor: str, sufijo: str) -> list[str]:
        """Si lo guardado ya no está entre las opciones (archivado), se agrega al final para no mostrar un select vacío."""
        if not isinstance(valor, str):
            return opciones
        if valor and valor not in opciones:
            opciones.append(valor if valor.endswith(")") else f"{valor} ({sufijo})")
        return opciones

    def _campos_cliente(self, d: dict, v: dict) -> list[dict]:
        return [{"key": "nombre", "label": "Nombre", "kind": "text", "value": v.get("nombre", ""),
                 "placeholder": "Nombre del cliente o de su empresa"},
                {"key": "notas", "label": "Notas", "kind": "text", "value": v.get("notas", ""),
                 "placeholder": "Sin teléfonos, correos ni documentos"}]

    def _campos_contrato(self, d: dict, v: dict) -> list[dict]:
        clientes = sorted((r["nombre"] for r in d["cliente"] if not r["archived"]), key=norm)
        cliente = v.get("cliente_id") if isinstance(v.get("cliente_id"), str) else ""
        opciones = self._con_valor(["(elige un cliente)", *clientes], cliente, "archivado")
        if cliente and cliente not in opciones:
            cliente = opciones[-1]
        return [{"key": "codigo", "label": "Código", "kind": "text", "value": v.get("codigo", ""),
                 "placeholder": "Por ejemplo RRC-2026-001"},
                {"key": "cliente_id", "label": "Cliente", "kind": "select", "value": cliente or "(elige un cliente)",
                 "options": opciones},
                {"key": "tipo", "label": "Tipo", "kind": "select", "value": v.get("tipo") or "(elige el tipo)",
                 "options": ["(elige el tipo)", "Pauta", "Patrocinio"]},
                {"key": "desde", "label": "Desde", "kind": "text", "value": v.get("desde", ""), "placeholder": "DD/MM/AAAA"},
                {"key": "hasta", "label": "Hasta", "kind": "text", "value": v.get("hasta", ""), "placeholder": "DD/MM/AAAA"},
                {"key": "valor_cop", "label": "Valor (COP)", "kind": "text", "value": v.get("valor_cop", ""),
                 "placeholder": "Opcional, por ejemplo 1.500.000"},
                {"key": "descripcion", "label": "Descripción", "kind": "text", "value": v.get("descripcion", ""),
                 "placeholder": "Opcional. En un patrocinio, escribe el programa o espacio patrocinado"}]

    def _campos_compromiso(self, d: dict, v: dict) -> list[dict]:
        contratos = sorted((r for r in d["contrato"] if not r["archived"]), key=lambda r: r["codigo"])
        op_con = self._con_valor(["(elige un contrato)", *(self._opcion_contrato(d, r) for r in contratos)],
                                 v.get("contrato_id", ""), "archivado")
        op_cuna = self._con_valor(["(elige una cuña)", *(f"{s['id']} · {s['title']}" for s in d["spots"])],
                                  v.get("asset_id", ""), "archivada")
        con, cuna = (v.get(k) if isinstance(v.get(k), str) else "" for k in ("contrato_id", "asset_id"))
        con = con if not con or con in op_con else op_con[-1]
        cuna = cuna if not cuna or cuna in op_cuna else op_cuna[-1]
        cantidad = v.get("cantidad", "")
        return [{"key": "contrato_id", "label": "Contrato", "kind": "select", "value": con or "(elige un contrato)",
                 "options": op_con},
                {"key": "asset_id", "label": "Cuña", "kind": "select", "value": cuna or "(elige una cuña)",
                 "options": op_cuna},
                {"key": "campana", "label": "Campaña", "kind": "text", "value": v.get("campana", ""),
                 "placeholder": "Opcional, por ejemplo Navidad"},
                {"key": "cantidad", "label": "Cantidad", "kind": "number", "value": "" if cantidad in (None, 0) else cantidad,
                 "placeholder": "Total de emisiones, por ejemplo 60"},
                {"key": "desde", "label": "Desde", "kind": "text", "value": v.get("desde", ""), "placeholder": "DD/MM/AAAA"},
                {"key": "hasta", "label": "Hasta", "kind": "text", "value": v.get("hasta", ""),
                 "placeholder": "DD/MM/AAAA (el día final cuenta)"},
                {"key": "franja_desde", "label": "Franja desde", "kind": "text", "value": v.get("franja_desde", ""),
                 "placeholder": "Opcional, HH:MM, por ejemplo 06:00"},
                {"key": "franja_hasta", "label": "Franja hasta", "kind": "text", "value": v.get("franja_hasta", ""),
                 "placeholder": "Opcional, HH:MM, por ejemplo 10:00"},
                {"key": "notas", "label": "Notas", "kind": "text", "value": v.get("notas", ""), "placeholder": "Opcional"}]
