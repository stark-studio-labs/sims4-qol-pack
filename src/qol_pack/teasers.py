"""
Freemium upgrade teasers -- tasteful in-game hints for uninstalled Stark mods.

When the QoL Pack detects that other Stark ecosystem mods are NOT installed,
it shows a single, dismissible teaser per game session. Teasers are:
- Max 1 per session (never spammy)
- Contextual (economy teaser near money UI, social near relationships, etc.)
- Dismissible with "Don't show again" option
- Disabled entirely via settings

Teaser types:
  Economy:  "Unlock banking, credit scores, and a stock market with Stark Economy"
  Social:   "Unlock 40-factor attraction and personality archetypes with Stark Social"
  Political: "Unlock elections, campaigns, and governance with Stark Political Sim"
  Drama:    "Unlock procedural storylines and consequence cascades with Stark Drama Engine"
  SmartSims: "Unlock AI-powered Sim behavior with Smart Sims"
"""

import time
from dataclasses import dataclass

from qol_pack._compat import Event, EventBus, ModRegistry, get_logger

from qol_pack.events import SettingsChangedEvent

log = get_logger("qol.teasers")

MOD_ID = "stark_qol_pack.teasers"

# ── Teaser Definitions ─────────────────────────────────────────────

TEASER_CATALOG = {
    "economy": {
        "mod_id": "stark_economy_sim",
        "title": "Stark Economy",
        "message": "Unlock banking, credit scores, and a stock market.",
        "context_hint": "Triggered near household funds interactions.",
        "url": "https://github.com/stark-studio-labs/sims4-economy-sim",
        "icon": "money",
    },
    "social": {
        "mod_id": "stark_social_sim",
        "title": "Stark Social Sim",
        "message": "Unlock 40-factor attraction and personality archetypes.",
        "context_hint": "Triggered near relationship panel interactions.",
        "url": "https://github.com/stark-studio-labs/sims4-social-sim",
        "icon": "relationship",
    },
    "political": {
        "mod_id": "stark_political_sim",
        "title": "Stark Political Sim",
        "message": "Unlock elections, campaigns, and governance.",
        "context_hint": "Triggered during in-game election season or career events.",
        "url": "https://github.com/stark-studio-labs/sims4-political-sim",
        "icon": "career",
    },
    "drama": {
        "mod_id": "stark_drama_engine",
        "title": "Stark Drama Engine",
        "message": "Unlock procedural storylines and consequence cascades.",
        "context_hint": "Triggered after dramatic life events.",
        "url": "https://github.com/stark-studio-labs/sims4-drama-engine",
        "icon": "drama",
    },
    "smart_sims": {
        "mod_id": "stark_smart_sims",
        "title": "Smart Sims",
        "message": "Unlock AI-powered personality-driven Sim behavior.",
        "context_hint": "Triggered when Sims make autonomy decisions.",
        "url": "https://github.com/stark-studio-labs/sims4-smart-sims",
        "icon": "brain",
    },
}


# ── Events ─────────────────────────────────────────────────────────

@dataclass
class TeaserShownEvent(Event):
    """Published when a teaser is displayed to the player."""
    teaser_key: str = ""
    title: str = ""
    message: str = ""

    def __post_init__(self):
        super().__init__()


@dataclass
class TeaserDismissedEvent(Event):
    """Published when the player dismisses a teaser."""
    teaser_key: str = ""
    permanently: bool = False

    def __post_init__(self):
        super().__init__()


# ── Core Teaser Manager ────────────────────────────────────────────

class TeaserManager:
    """Manages freemium upgrade teasers with session-level rate limiting.

    Rules:
    - At most 1 teaser per game session
    - Never show a teaser for a mod that IS installed
    - Never show a teaser the player permanently dismissed
    - Teasers are contextual: only fire when a relevant game action occurs
    - Entire system disabled via settings key "teasers.enabled"
    """

    _enabled = True
    _shown_this_session = False
    _session_teaser_key = None
    _permanently_dismissed: set = set()
    _installed_mods: set = set()
    _session_start_time = 0.0

    @classmethod
    def install(cls):
        """Initialize the teaser system. Scans installed mods."""
        cls._session_start_time = time.time()
        cls._shown_this_session = False
        cls._session_teaser_key = None
        cls._scan_installed_mods()

        EventBus.subscribe(
            SettingsChangedEvent,
            cls._on_settings_changed,
            priority=90,
            mod_id=MOD_ID,
        )

        log.info(
            "Teaser system installed",
            enabled=cls._enabled,
            installed_stark_mods=list(cls._installed_mods),
            dismissed=list(cls._permanently_dismissed),
        )

    @classmethod
    def reset(cls):
        """Reset all state (for testing)."""
        cls._enabled = True
        cls._shown_this_session = False
        cls._session_teaser_key = None
        cls._permanently_dismissed = set()
        cls._installed_mods = set()
        cls._session_start_time = 0.0

    @classmethod
    def _on_settings_changed(cls, event):
        """React to settings changes."""
        if event.key == "teasers.enabled":
            cls._enabled = bool(event.new_value)
            log.info("Teasers %s", "enabled" if cls._enabled else "disabled")
        elif event.key == "teasers.dismissed":
            cls._permanently_dismissed = set(event.new_value)

    @classmethod
    def _scan_installed_mods(cls):
        """Check which Stark ecosystem mods are installed."""
        cls._installed_mods = set()
        registered = ModRegistry.all_mods()
        for teaser_key, teaser_info in TEASER_CATALOG.items():
            if teaser_info["mod_id"] in registered:
                cls._installed_mods.add(teaser_key)

    @classmethod
    def get_eligible_teasers(cls):
        """Return teaser keys that could be shown (not installed, not dismissed).

        Returns:
            List of teaser key strings.
        """
        eligible = []
        for key in TEASER_CATALOG:
            if key in cls._installed_mods:
                continue
            if key in cls._permanently_dismissed:
                continue
            eligible.append(key)
        return eligible

    @classmethod
    def can_show_teaser(cls):
        """Check if a teaser is allowed right now.

        Returns:
            True if a teaser can be shown (enabled, none shown this session,
            at least one eligible teaser exists).
        """
        if not cls._enabled:
            return False
        if cls._shown_this_session:
            return False
        return len(cls.get_eligible_teasers()) > 0

    @classmethod
    def try_show(cls, context_key):
        """Attempt to show a teaser for the given context.

        This is the main entry point. Modules call this when a contextually
        relevant game action occurs (e.g., UITweaks calls try_show("economy")
        when the player clicks the money display).

        Args:
            context_key: One of "economy", "social", "political", "drama", "smart_sims".

        Returns:
            The teaser info dict if shown, None if suppressed.
        """
        if not cls.can_show_teaser():
            return None

        if context_key not in TEASER_CATALOG:
            log.debug("Unknown teaser context", context=context_key)
            return None

        if context_key in cls._installed_mods:
            return None

        if context_key in cls._permanently_dismissed:
            return None

        teaser = TEASER_CATALOG[context_key]

        cls._shown_this_session = True
        cls._session_teaser_key = context_key

        EventBus.publish(
            TeaserShownEvent(
                teaser_key=context_key,
                title=teaser["title"],
                message=teaser["message"],
            ),
            source_mod=MOD_ID,
        )

        log.info("Teaser shown", key=context_key, title=teaser["title"])

        # In-game this would call _show_notification(); outside game it's a no-op
        _show_notification(teaser)

        return teaser

    @classmethod
    def dismiss(cls, teaser_key, permanently=False):
        """Dismiss a teaser.

        Args:
            teaser_key: The teaser to dismiss.
            permanently: If True, never show this teaser again.
        """
        if permanently:
            cls._permanently_dismissed.add(teaser_key)

        EventBus.publish(
            TeaserDismissedEvent(
                teaser_key=teaser_key,
                permanently=permanently,
            ),
            source_mod=MOD_ID,
        )

        log.info("Teaser dismissed", key=teaser_key, permanent=permanently)

    @classmethod
    def get_status(cls):
        """Return current teaser system status.

        Returns:
            Dict with enabled, shown_this_session, eligible teasers, dismissed list.
        """
        return {
            "enabled": cls._enabled,
            "shown_this_session": cls._shown_this_session,
            "session_teaser_key": cls._session_teaser_key,
            "eligible": cls.get_eligible_teasers(),
            "installed_stark_mods": list(cls._installed_mods),
            "permanently_dismissed": list(cls._permanently_dismissed),
        }

    @classmethod
    def load_dismissed(cls, dismissed_keys):
        """Load permanently dismissed teasers from saved settings.

        Args:
            dismissed_keys: List of teaser key strings.
        """
        cls._permanently_dismissed = set(dismissed_keys)

    @classmethod
    def mark_mod_installed(cls, teaser_key):
        """Mark a mod as installed (suppresses its teaser).

        Useful when mods are installed mid-session.
        """
        cls._installed_mods.add(teaser_key)


# ── Internal helpers ───────────────────────────────────────────────

def _show_notification(teaser):
    """Show an in-game notification for a teaser.

    Uses the game's notification system when available; no-op outside game.
    """
    try:
        from stark_framework.services.notification_service import NotificationService
        NotificationService.show(
            title=f"Upgrade Available: {teaser['title']}",
            message=teaser["message"],
            icon=teaser.get("icon", "info"),
            urgency="low",
            actions=[
                {"label": "Learn More", "url": teaser["url"]},
                {"label": "Dismiss", "callback": "teaser_dismiss"},
                {"label": "Don't Show Again", "callback": "teaser_dismiss_permanent"},
            ],
        )
    except (ImportError, AttributeError):
        # Outside game or NotificationService not available -- silent
        pass
