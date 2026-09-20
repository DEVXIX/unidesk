.pragma library
// What the Customize panel offers for each widget type, and the Add menu.
// kind: bool | choice | slider | text. `def` must match the widget's default.

var types = [
    { type: "time",     label: "Time",          icon: "schedule" },
    { type: "clock",    label: "Analog clock",  icon: "schedule" },
    { type: "media",    label: "Music",         icon: "music_note" },
    { type: "system",   label: "System stat",   icon: "monitor_heart" },
    { type: "weather",  label: "Weather",       icon: "partly_cloudy_day" },
    { type: "calendar", label: "Calendar",      icon: "calendar_month" },
    { type: "profile",  label: "Profile",       icon: "lock" },
    { type: "github",   label: "Code activity", icon: "commit" },
    { type: "picture",  label: "Picture",       icon: "star" },
    { type: "network",  label: "Network speed", icon: "swap_vert" },
    { type: "storage",  label: "Storage",       icon: "hard_drive" },
    { type: "clipboard", label: "Clipboard",    icon: "content_paste" },
    { type: "notifications", label: "Notifications", icon: "notifications" },
    { type: "mixer",    label: "Volume mixer",  icon: "headphones" },
    { type: "notes",    label: "Note / to-do",  icon: "sticky_note_2" },
    { type: "timer",    label: "Timer / Pomodoro", icon: "timer" },
    { type: "launcher", label: "Launcher",      icon: "apps" },
    { type: "games",    label: "Recent games",  icon: "sports_esports" },
    { type: "league",   label: "League of Legends", icon: "emoji_events" },
    { type: "countdown", label: "Countdown",    icon: "hourglass_top" },
    { type: "slideshow", label: "Photo slideshow", icon: "photo_library" },
    { type: "quote",    label: "Quote of the day", icon: "format_quote" },
    { type: "dev",      label: "Code reviews & CI", icon: "merge" },
    { type: "devices",  label: "Batteries",     icon: "battery_full" },
    { type: "xd",       label: "xD",            icon: "apps" },
    { type: "ssh",      label: "Terminal (SSH)",  icon: "terminal" },
    { type: "bucket",   label: "S3 / MinIO storage", icon: "cloud" }
];

var tones = ["primary", "secondary", "tertiary", "surface"];

var fields = {
    time: [
        { key: "size", label: "Text size", kind: "slider", min: 60, max: 280, step: 5, def: 150 },
        { key: "format", label: "Format", kind: "choice", options: ["24h", "12h"], def: "24h" },
        { key: "seconds", label: "Seconds", kind: "bool", def: false },
        { key: "date", label: "Date line", kind: "bool", def: true }
    ],
    clock: [
        { key: "size", label: "Size", kind: "slider", min: 120, max: 420, step: 10, def: 240 },
        { key: "seconds", label: "Seconds dot", kind: "bool", def: true },
        { key: "quote", label: "Quote", kind: "text", def: "" }
    ],
    media: [
        { key: "style", label: "Style", kind: "choice", options: ["card", "poster"], def: "card" },
        { key: "width", label: "Width", kind: "slider", min: 300, max: 700, step: 10, def: 420 },
        { key: "lyrics", label: "Lyrics", kind: "bool", def: true },
        { key: "lyric_lines", label: "Lyric lines", kind: "slider", min: 3, max: 13, step: 2, def: 7 }
    ],
    system: [
        { key: "metric", label: "Shows", kind: "choice", options: ["cpu", "ram", "disk", "gpu", "gpu-temp", "cpu-temp", "vram"], def: "cpu" },
        { key: "tone", label: "Colour", kind: "choice", options: tones, def: "primary" },
        { key: "width", label: "Width", kind: "slider", min: 100, max: 260, step: 5, def: 130 },
        { key: "height", label: "Height", kind: "slider", min: 90, max: 220, step: 5, def: 118 }
    ],
    weather: [
        { key: "tone", label: "Colour", kind: "choice", options: tones, def: "primary" },
        { key: "width", label: "Width", kind: "slider", min: 320, max: 600, step: 10, def: 420 }
    ],
    calendar: [
        { key: "view", label: "View", kind: "choice", options: ["week", "month"], def: "week" },
        { key: "week_starts", label: "Week starts", kind: "choice", options: ["monday", "sunday"], def: "monday" },
        { key: "width", label: "Width", kind: "slider", min: 240, max: 420, step: 10, def: 280 }
    ],
    profile: [
        { key: "background", label: "Background", kind: "choice", options: ["wallpaper", "artwork"], def: "wallpaper" },
        { key: "avatar", label: "Avatar (github or image path)", kind: "text", def: "github" },
        { key: "width", label: "Width", kind: "slider", min: 240, max: 400, step: 10, def: 280 }
    ],
    github: [
        { key: "weeks", label: "Weeks shown", kind: "slider", min: 8, max: 52, step: 1, def: 24 },
        { key: "activity", label: "Activity rows", kind: "slider", min: 0, max: 6, step: 1, def: 3 },
        { key: "width", label: "Width", kind: "slider", min: 340, max: 640, step: 10, def: 430 }
    ],
    picture: [
        { key: "src", label: "Image (path, wallpaper or artwork)", kind: "text", def: "wallpaper" },
        { key: "shape", label: "Shape", kind: "choice", options: ["star", "cookie", "burst", "clover", "squircle", "circle", "rounded"], def: "star" },
        { key: "size", label: "Size", kind: "slider", min: 120, max: 900, step: 10, def: 400 }
    ],
    network: [
        { key: "units", label: "Units", kind: "choice", options: ["bytes", "bits"], def: "bytes" },
        { key: "graph", label: "Graph", kind: "bool", def: true },
        { key: "tone", label: "Colour", kind: "choice", options: tones, def: "surface" },
        { key: "width", label: "Width", kind: "slider", min: 240, max: 560, step: 10, def: 320 }
    ],
    storage: [
        { key: "drives", label: "Drives (all, or e.g. C D)", kind: "text", def: "all" },
        { key: "tone", label: "Colour", kind: "choice", options: tones, def: "surface" },
        { key: "width", label: "Width", kind: "slider", min: 240, max: 560, step: 10, def: 320 }
    ],
    clipboard: [
        { key: "items", label: "Rows shown (scroll for more)", kind: "slider", min: 2, max: 10, step: 1, def: 5 },
        { key: "images", label: "Keep copied images", kind: "bool", def: true },
        { key: "width", label: "Width", kind: "slider", min: 260, max: 560, step: 10, def: 340 }
    ],
    mixer: [
        { key: "rows", label: "Apps shown before scrolling", kind: "slider", min: 2, max: 8, step: 1, def: 3 },
        { key: "width", label: "Width", kind: "slider", min: 280, max: 480, step: 10, def: 360 }
    ],
    notes: [
        { key: "mode", label: "Kind", kind: "choice", options: ["note", "todo"], def: "note" },
        { key: "title", label: "Title", kind: "text", def: "" },
        { key: "tone", label: "Colour", kind: "choice", options: ["tertiary", "primary", "secondary", "surface"], def: "tertiary" },
        { key: "font_size", label: "Text size", kind: "slider", min: 12, max: 24, step: 1, def: 15 },
        { key: "width", label: "Width", kind: "slider", min: 220, max: 480, step: 10, def: 300 },
        { key: "height", label: "Height (note)", kind: "slider", min: 140, max: 460, step: 10, def: 220 }
    ],
    timer: [
        { key: "size", label: "Size", kind: "slider", min: 160, max: 340, step: 10, def: 230 },
        { key: "pomodoro", label: "Pomodoro (focus / break)", kind: "bool", def: true },
        { key: "focus_minutes", label: "Focus minutes", kind: "slider", min: 5, max: 90, step: 5, def: 25 },
        { key: "break_minutes", label: "Break minutes", kind: "slider", min: 1, max: 30, step: 1, def: 5 },
        { key: "pause_music", label: "Pause music when time's up", kind: "bool", def: false },
        { key: "auto_continue", label: "Start the next session automatically", kind: "bool", def: false }
    ],
    launcher: [
        { key: "items", label: "Shortcuts (one per line: path, URL, or Name | target)", kind: "lines", def: "%USERPROFILE%\\Downloads\nms-settings:\nhttps://github.com\nC:\\Windows\\explorer.exe" },
        { key: "columns", label: "Columns", kind: "slider", min: 2, max: 8, step: 1, def: 4 },
        { key: "tile", label: "Tile size", kind: "slider", min: 56, max: 110, step: 2, def: 76 }
    ],
    games: [
        { key: "title", label: "Title", kind: "text", def: "Jump back in" },
        { key: "count", label: "Games shown", kind: "slider", min: 2, max: 10, step: 1, def: 5 },
        { key: "cover_width", label: "Cover size", kind: "slider", min: 70, max: 150, step: 2, def: 96 }
    ],
    league: [
        { key: "queue", label: "Queue", kind: "choice", options: ["solo", "flex"], def: "solo" },
        { key: "preview_tier", label: "Preview rank (see how a tier looks)", kind: "choice", options: ["off", "Iron", "Bronze", "Silver", "Gold", "Platinum", "Emerald", "Diamond", "Master", "Grandmaster", "Challenger"], def: "off" },
        { key: "preview_lp", label: "Preview LP", kind: "slider", min: 0, max: 3000, step: 1, def: 1287 },
        { key: "games", label: "Recent games shown", kind: "slider", min: 3, max: 10, step: 1, def: 7 },
        { key: "width", label: "Width", kind: "slider", min: 340, max: 500, step: 10, def: 390 }
    ],
    countdown: [
        { key: "label", label: "What for", kind: "text", def: "New Year" },
        { key: "date", label: "Date (YYYY-MM-DD)", kind: "text", def: "" },
        { key: "shape", label: "Shape", kind: "choice", options: ["burst", "cookie", "star", "flower", "clover", "squircle", "circle"], def: "burst" },
        { key: "size", label: "Size", kind: "slider", min: 150, max: 340, step: 10, def: 210 }
    ],
    slideshow: [
        { key: "folder", label: "Folder", kind: "text", def: "%USERPROFILE%\\Pictures" },
        { key: "interval", label: "Seconds per photo", kind: "slider", min: 3, max: 120, step: 1, def: 12 },
        { key: "shuffle", label: "Shuffle", kind: "bool", def: true },
        { key: "shape", label: "Shape", kind: "choice", options: ["squircle", "rounded", "cookie", "star", "burst", "clover", "circle"], def: "squircle" },
        { key: "size", label: "Size", kind: "slider", min: 180, max: 900, step: 10, def: 360 }
    ],
    quote: [
        { key: "quotes", label: "Your quotes (one per line: text \u2014 author). Empty = built-in", kind: "lines", def: "" },
        { key: "tone", label: "Colour", kind: "choice", options: ["surface", "primary", "secondary", "tertiary"], def: "surface" },
        { key: "font_size", label: "Text size", kind: "slider", min: 13, max: 30, step: 1, def: 18 },
        { key: "width", label: "Width", kind: "slider", min: 260, max: 600, step: 10, def: 360 }
    ],
    dev: [
        { key: "rows", label: "Rows", kind: "slider", min: 3, max: 10, step: 1, def: 5 },
        { key: "ci_repos", label: "CI repos (one per line: github:owner/repo or gitea:owner/repo)", kind: "lines", def: "" },
        { key: "width", label: "Width", kind: "slider", min: 360, max: 580, step: 10, def: 420 }
    ],
    devices: [
        { key: "width", label: "Width", kind: "slider", min: 260, max: 440, step: 10, def: 320 }
    ],
    notifications: [
        { key: "items", label: "Rows shown (scroll for more)", kind: "slider", min: 1, max: 8, step: 1, def: 4 },
        { key: "text", label: "Message text", kind: "bool", def: true },
        { key: "width", label: "Width", kind: "slider", min: 280, max: 560, step: 10, def: 360 }
    ],
    xd: [
        { key: "width", label: "Width", kind: "slider", min: 280, max: 520, step: 10, def: 340 },
        { key: "height", label: "Height", kind: "slider", min: 280, max: 640, step: 20, def: 400 }
    ],
    bucket: [
        { key: "label", label: "Name", kind: "text", def: "" },
        { key: "width", label: "Width", kind: "slider", min: 280, max: 640, step: 10, def: 380 },
        { key: "height", label: "Height", kind: "slider", min: 220, max: 800, step: 20, def: 420 }
    ],
    ssh: [
        { key: "layout", label: "Panes", kind: "choice", options: ["1x1", "2x1", "2x2"], def: "1x1" },
        { key: "label", label: "Name", kind: "text", def: "" },
        { key: "width", label: "Width", kind: "slider", min: 320, max: 1200, step: 20, def: 520 },
        { key: "height", label: "Height", kind: "slider", min: 200, max: 900, step: 20, def: 300 }
    ]
};

function labelFor(type) {
    for (var i = 0; i < types.length; i++) if (types[i].type === type) return types[i].label;
    return type;
}
