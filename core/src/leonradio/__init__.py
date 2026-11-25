"""`import leonradio as lr` — API pública para addons."""

from leonradio_core.sdk import (  # noqa: F401
    API_VERSION,
    Context,
    Editor,
    PermissionDenied,
    command,
    register_command,
    register_editor,
    unregister_editor,
)
from leonradio_core.uischema import UI  # noqa: F401
