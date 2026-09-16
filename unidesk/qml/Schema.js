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
    { type: "picture",  label: "Picture",       icon: "star" }
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
        { key: "metric", label: "Shows", kind: "choice", options: ["cpu", "ram", "disk", "gpu", "gpu-temp", "vram"], def: "cpu" },
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
    ]
};

function labelFor(type) {
    for (var i = 0; i < types.length; i++) if (types[i].type === type) return types[i].label;
    return type;
}
