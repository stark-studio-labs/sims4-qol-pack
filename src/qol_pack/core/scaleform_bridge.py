"""
Scaleform GFx UI Bridge -- Python-to-Flash ExternalInterface abstraction.

Intercepts Flash ExternalInterface calls from the Sims 4 Scaleform GFx UI
layer and routes them to registered Python handlers. This is the mechanism
UI Cheats Extension uses internally; the Stark QoL Pack provides its own
clean abstraction over the same pattern.

Zero idle cost -- entirely event-driven. Handlers fire only when
Scaleform dispatches a click event through the ExternalInterface bridge.
No polling, no tick registration, no per-frame overhead.

Usage:
    from qol_pack.core.scaleform_bridge import ScaleformBridge, UIClickEvent

    def on_need_bar_click(event: UIClickEvent):
        print(f"Sim {event.sim_id} clicked {event.element_id} at ({event.x}, {event.y})")

    ScaleformBridge.register_click_handler("need_bar", "left", on_need_bar_click)
    ScaleformBridge.register_click_handler("need_bar", "right", on_need_bar_click)
"""

from dataclasses import dataclass, field
from qol_pack._compat import Event, EventBus, Diagnostics, get_logger

from qol_pack.modules.ui_tweaks import EDITABLE_FIELDS

# Game API imports -- graceful degradation outside the game (for tests)
try:
    from distributor.system import Distributor  # type: ignore[import-not-found]
    _HAS_DISTRIBUTOR = True
except ImportError:
    Distributor = None
    _HAS_DISTRIBUTOR = False

try:
    from ui.ui_dialog import UiDialogBase  # type: ignore[import-not-found]
    _HAS_UI_DIALOG = True
except ImportError:
    UiDialogBase = None
    _HAS_UI_DIALOG = False

try:
    import sims4.commands  # type: ignore[import-not-found]
    _HAS_COMMANDS = True
except ImportError:
    sims4 = None
    _HAS_COMMANDS = False

log = get_logger("qol.scaleform_bridge")

MOD_ID = "stark_qol_pack.scaleform_bridge"

VALID_CLICK_TYPES = ("left", "right")


# ── Events ────────────────────────────────────────────────────────────

@dataclass
class UIClickEvent(Event):
    """Published when Scaleform dispatches a click through ExternalInterface.

    Handlers receive this with the element that was clicked, what kind of
    click it was, screen coordinates, and which Sim (if any) was active.
    """
    element_id: str = ""
    click_type: str = "left"  # "left" or "right"
    x: float = 0.0
    y: float = 0.0
    sim_id: int = 0

    def __post_init__(self):
        super().__init__()


@dataclass
class ScaleformMessageEvent(Event):
    """Published when a raw ExternalInterface message is received.

    Lower-level than UIClickEvent -- used for diagnostics and debugging.
    """
    method_name: str = ""
    args: tuple = ()
    source_element: str = ""

    def __post_init__(self):
        super().__init__()


# ── Value Validation ──────────────────────────────────────────────────

class ValueValidator:
    """Validates and clamps values against EDITABLE_FIELDS definitions.

    Pulls min/max ranges from ui_tweaks.EDITABLE_FIELDS so validation
    rules are defined in one place.
    """

    @staticmethod
    def clamp(value, minimum, maximum):
        """Clamp a numeric value to [minimum, maximum].

        Args:
            value: The value to clamp.
            minimum: Lower bound (inclusive).
            maximum: Upper bound (inclusive).

        Returns:
            The clamped value.
        """
        return max(minimum, min(maximum, value))

    @staticmethod
    def validate_range(field_name, value):
        """Validate and clamp a value against the field's defined range.

        Args:
            field_name: Key from EDITABLE_FIELDS (e.g. "need_hunger").
            value: The raw value to validate.

        Returns:
            The clamped value if the field exists, or the original value
            if the field is unknown (logged as a warning).
        """
        field_info = EDITABLE_FIELDS.get(field_name)
        if field_info is None:
            log.warn("Unknown field for validation", field=field_name)
            return value
        return ValueValidator.clamp(value, field_info["min"], field_info["max"])


# ── Click Handler Registry ────────────────────────────────────────────

class ClickHandlerRegistry:
    """Maps (element_id, click_type) pairs to handler functions.

    Internal registry used by ScaleformBridge. Not intended for direct
    use -- call ScaleformBridge.register_click_handler() instead.
    """

    _handlers: dict = {}  # (element_id, click_type) -> handler_fn

    @classmethod
    def register(cls, element_id, click_type, handler_fn):
        """Register a handler for a specific element + click combination.

        Args:
            element_id: The Scaleform UI element identifier.
            click_type: "left" or "right".
            handler_fn: Callable that accepts a UIClickEvent.

        Raises:
            ValueError: If click_type is not "left" or "right".
        """
        if click_type not in VALID_CLICK_TYPES:
            raise ValueError(
                f"Invalid click_type '{click_type}' -- must be one of {VALID_CLICK_TYPES}"
            )
        key = (element_id, click_type)
        cls._handlers[key] = handler_fn
        log.debug("Handler registered", element_id=element_id, click_type=click_type)

    @classmethod
    def unregister(cls, element_id, click_type):
        """Remove a handler for a specific element + click combination.

        Args:
            element_id: The Scaleform UI element identifier.
            click_type: "left" or "right".

        Returns:
            True if a handler was removed, False if none was registered.
        """
        key = (element_id, click_type)
        if key in cls._handlers:
            del cls._handlers[key]
            log.debug("Handler unregistered", element_id=element_id, click_type=click_type)
            return True
        return False

    @classmethod
    def get_handler(cls, element_id, click_type):
        """Look up the handler for an element + click combination.

        Returns:
            The handler function, or None if not registered.
        """
        return cls._handlers.get((element_id, click_type))

    @classmethod
    def has_handler(cls, element_id, click_type):
        """Check if a handler is registered for this combination."""
        return (element_id, click_type) in cls._handlers

    @classmethod
    def clear(cls):
        """Remove all registered handlers. Used during teardown/testing."""
        cls._handlers.clear()
        log.debug("All click handlers cleared")

    @classmethod
    def registered_count(cls):
        """Return the number of registered handlers."""
        return len(cls._handlers)


# ── Scaleform Bridge ──────────────────────────────────────────────────

class ScaleformBridge:
    """Abstracts the Sims 4 Python-to-Flash ExternalInterface message bridge.

    Intercepts UI click events from Scaleform GFx and dispatches them to
    registered handlers via the ClickHandlerRegistry. Publishes events
    on the Stark Framework EventBus for observability.

    The bridge is entirely event-driven -- it installs a hook on the game's
    ExternalInterface dispatch path and fires only when clicks arrive.
    """

    _installed = False
    _original_handler = None  # Preserved reference to the game's original handler

    @classmethod
    def install(cls):
        """Install the Scaleform ExternalInterface intercept.

        Hooks into the game's UI dialog dispatch to capture click events
        from Flash. Safe to call multiple times -- subsequent calls are no-ops.
        """
        if cls._installed:
            log.debug("ScaleformBridge already installed, skipping")
            return

        _install_flash_intercept(cls._on_external_interface_call)
        cls._installed = True
        log.info(
            "ScaleformBridge installed",
            has_distributor=_HAS_DISTRIBUTOR,
            has_ui_dialog=_HAS_UI_DIALOG,
        )

    @classmethod
    def uninstall(cls):
        """Remove the Scaleform intercept and clean up.

        Restores the original handler if one was saved. Clears all
        registered click handlers.
        """
        if not cls._installed:
            return

        _uninstall_flash_intercept(cls._original_handler)
        ClickHandlerRegistry.clear()
        cls._installed = False
        cls._original_handler = None
        log.info("ScaleformBridge uninstalled")

    @classmethod
    def register_click_handler(cls, element_id, click_type, handler_fn):
        """Register a handler for a UI element click.

        Args:
            element_id: The Scaleform UI element identifier (e.g. "need_bar").
            click_type: "left" or "right".
            handler_fn: Callable(UIClickEvent) -> None.
        """
        ClickHandlerRegistry.register(element_id, click_type, handler_fn)

    @classmethod
    def unregister_click_handler(cls, element_id, click_type):
        """Remove a click handler.

        Args:
            element_id: The Scaleform UI element identifier.
            click_type: "left" or "right".

        Returns:
            True if a handler was removed, False if none existed.
        """
        return ClickHandlerRegistry.unregister(element_id, click_type)

    @classmethod
    def _on_external_interface_call(cls, method_name, *args):
        """Internal callback invoked by the ExternalInterface intercept.

        Parses the raw Scaleform message, constructs a UIClickEvent if
        applicable, and dispatches to the registered handler.

        Args:
            method_name: The ExternalInterface method name from Flash.
            *args: Arguments passed from the Flash call.
        """
        # Publish raw message event for diagnostics
        source_element = _extract_element_id(method_name, args)
        EventBus.publish(
            ScaleformMessageEvent(
                method_name=method_name,
                args=args,
                source_element=source_element,
            ),
            source_mod=MOD_ID,
        )

        # Parse click events
        click_type = _parse_click_type(method_name)
        if click_type is None:
            return  # Not a click event we handle

        element_id = source_element
        if not element_id:
            return

        handler = ClickHandlerRegistry.get_handler(element_id, click_type)
        if handler is None:
            return  # No handler registered for this element + click

        x, y = _extract_coordinates(args)
        sim_id = _extract_sim_id(args)

        event = UIClickEvent(
            element_id=element_id,
            click_type=click_type,
            x=x,
            y=y,
            sim_id=sim_id,
        )

        EventBus.publish(event, source_mod=MOD_ID)

        if event.cancelled:
            log.debug("Click event cancelled", element_id=element_id, click_type=click_type)
            return

        try:
            handler(event)
        except Exception as exc:
            log.error(
                "Click handler error",
                element_id=element_id,
                click_type=click_type,
                error=str(exc),
            )
            Diagnostics.record_error(
                mod_id=MOD_ID,
                error=exc,
                context=f"Handling click: {element_id}/{click_type}",
            )


# ── Internal helpers (game API wrappers) ──────────────────────────────

def _install_flash_intercept(callback):
    """Hook into the game's ExternalInterface dispatch.

    The Sims 4 routes Flash ExternalInterface calls through the Distributor
    and UiDialogBase systems. We intercept at the dialog response level
    to capture click events without modifying core game code.

    Args:
        callback: Function to call when an ExternalInterface message arrives.
    """
    if not _HAS_UI_DIALOG or UiDialogBase is None:
        log.warn("UiDialogBase not available -- intercept not installed (test mode)")
        return

    try:
        # Store original handler for clean uninstall
        original = getattr(UiDialogBase, '_handle_external_interface', None)
        ScaleformBridge._original_handler = original

        def _intercept_handler(dialog_self, method_name, *args, **kwargs):
            # Fire our callback first
            try:
                callback(method_name, *args)
            except Exception as exc:
                log.error("Intercept callback error", error=str(exc))

            # Call the original handler so the game functions normally
            if original is not None:
                return original(dialog_self, method_name, *args, **kwargs)

        UiDialogBase._handle_external_interface = _intercept_handler
        log.debug("Flash ExternalInterface intercept installed")
    except (AttributeError, TypeError) as exc:
        log.error("Failed to install Flash intercept", error=str(exc))


def _uninstall_flash_intercept(original_handler):
    """Restore the original ExternalInterface handler.

    Args:
        original_handler: The original method reference saved during install.
    """
    if not _HAS_UI_DIALOG or UiDialogBase is None:
        return

    try:
        if original_handler is not None:
            UiDialogBase._handle_external_interface = original_handler
            log.debug("Flash ExternalInterface intercept removed -- original restored")
        else:
            # No original existed; remove our intercept entirely
            if hasattr(UiDialogBase, '_handle_external_interface'):
                delattr(UiDialogBase, '_handle_external_interface')
            log.debug("Flash ExternalInterface intercept removed")
    except (AttributeError, TypeError) as exc:
        log.error("Failed to uninstall Flash intercept", error=str(exc))


def _extract_element_id(method_name, args):
    """Extract the UI element identifier from a Scaleform message.

    The element ID is typically encoded as the first argument or
    embedded in the method name (e.g. "click_need_bar" -> "need_bar").

    Args:
        method_name: The ExternalInterface method name.
        args: Arguments from the Flash call.

    Returns:
        The element ID string, or empty string if not found.
    """
    # Convention: first string arg is often the element ID
    for arg in args:
        if isinstance(arg, str) and arg:
            return arg

    # Fallback: parse from method name (strip click_ / rightclick_ prefix)
    if method_name.startswith("click_"):
        return method_name[6:]
    if method_name.startswith("rightclick_"):
        return method_name[11:]

    return ""


def _parse_click_type(method_name):
    """Determine click type from the ExternalInterface method name.

    Args:
        method_name: The ExternalInterface method name.

    Returns:
        "left", "right", or None if not a click event.
    """
    name_lower = method_name.lower()
    if "rightclick" in name_lower or "right_click" in name_lower:
        return "right"
    if "click" in name_lower:
        return "left"
    return None


def _extract_coordinates(args):
    """Extract (x, y) screen coordinates from Scaleform arguments.

    Scaleform typically passes coordinates as numeric arguments.
    Convention: first two numeric args after the element ID are x, y.

    Args:
        args: Arguments from the Flash call.

    Returns:
        Tuple of (x, y) floats. Defaults to (0.0, 0.0) if not found.
    """
    numerics = [a for a in args if isinstance(a, (int, float))]
    if len(numerics) >= 2:
        return (float(numerics[0]), float(numerics[1]))
    return (0.0, 0.0)


def _extract_sim_id(args):
    """Extract the active Sim's ID from Scaleform arguments.

    The sim_id is typically a large integer passed in the arguments.
    If not found in args, falls back to the active Sim from game services.

    Args:
        args: Arguments from the Flash call.

    Returns:
        The sim_id as an int, or 0 if unavailable.
    """
    # Look for a large integer (sim IDs are typically > 1000)
    for arg in args:
        if isinstance(arg, int) and arg > 1000:
            return arg

    # Fallback: get active Sim from game services
    try:
        import services  # type: ignore[import-not-found]
        client = services.client_manager().get_first_client()
        if client is not None and client.active_sim is not None:
            return client.active_sim.sim_id
    except (ImportError, AttributeError):
        pass

    return 0
