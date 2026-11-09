from textual.theme import Theme

# 1. night: Minimalist high-contrast dark
NIGHT = Theme(
    name="night",
    primary="#ffffff",
    secondary="#737373",
    accent="#ffffff",
    foreground="#ededed",
    background="#0a0a0a",
    surface="#0a0a0a",
    panel="#171717",
    success="#22c55e",
    warning="#facc15",
    error="#ef4444",
    dark=True,
)

# 2. morning: Warm pastel yellowish light
MORNING = Theme(
    name="morning",
    primary="#9a3412",
    secondary="#78716c",
    accent="#c2410c",
    foreground="#1c1917",
    background="#faf6ee",
    surface="#faf6ee",
    panel="#efe8d8",
    success="#16a34a",
    warning="#d97706",
    error="#dc2626",
    dark=False,
)

# 3. tokyo-night: Tokyo Night
TOKYO_NIGHT = Theme(
    name="tokyo-night",
    primary="#7aa2f7",
    secondary="#565f89",
    accent="#bb9af7",
    foreground="#c0caf5",
    background="#1a1b26",
    surface="#1a1b26",
    panel="#24283b",
    success="#9ece6a",
    warning="#e0af68",
    error="#f7768e",
    dark=True,
)

# 4. nord: Arctic Nord
NORD = Theme(
    name="nord",
    primary="#88c0d0",
    secondary="#7b88a1",
    accent="#81a1c1",
    foreground="#eceff4",
    background="#2e3440",
    surface="#2e3440",
    panel="#3b4252",
    success="#a3be8c",
    warning="#ebcb8b",
    error="#bf616a",
    dark=True,
)

# 5. dracula: Dracula
DRACULA = Theme(
    name="dracula",
    primary="#bd93f9",
    secondary="#6272a4",
    accent="#ff79c6",
    foreground="#f8f8f2",
    background="#282a36",
    surface="#282a36",
    panel="#343746",
    success="#50fa7b",
    warning="#f1fa8c",
    error="#ff5555",
    dark=True,
)

ROOSTR_THEMES = [NIGHT, MORNING, TOKYO_NIGHT, NORD, DRACULA]
THEME_NAMES = ["night", "morning", "tokyo-night", "nord", "dracula"]
DEFAULT_THEME = "night"
