// ==WindhawkMod==
// @id              unidesk-classic-ui
// @name            unidesk colours for classic apps
// @description     Menus, menu bars, scroll bars, status bars and toolbars of classic Windows apps in unidesk's live Material You colours
// @version         1.0
// @author          unidesk
// @include         *
// @compilerOptions -luxtheme -lgdi32 -ladvapi32
// ==/WindhawkMod==

// ==WindhawkModReadme==
/*
# unidesk colours for classic apps

Paints the parts of classic Windows apps that Windows' theme draws — menu bars,
right-click and drop-down menus, scroll bars, status bars and toolbars — in the
colours unidesk takes from your album art or wallpaper. When the colours change
in unidesk, apps pick them up the next time they redraw.

Needs unidesk with **Settings > Theme other apps** turned on (it publishes its
palette for this mod). Without it, apps look exactly as before.

What it can't reach: apps that draw their own interface (browsers, Electron
apps like VS Code or Discord, and new Windows 11 apps like Paint or Settings).
unidesk themes VS Code and Windows Terminal separately.

Open apps change the next time they redraw; if one doesn't, restart it.
*/
// ==/WindhawkModReadme==

// ==WindhawkModSettings==
/*
- menus: true
  $name: Menus and menu bars
- scrollbars: true
  $name: Scroll bars
- statusbars: true
  $name: Status bars
- toolbars: true
  $name: Toolbars
*/
// ==/WindhawkModSettings==

#include <windhawk_utils.h>

#include <commctrl.h>
#include <uxtheme.h>
#include <vssym32.h>

#include <algorithm>
#include <atomic>

// ---- the palette unidesk publishes -------------------------------------------------------

namespace {

const wchar_t kPaletteKey[] = L"Software\\unidesk\\Palette";

struct Palette {
    bool enabled = false;
    COLORREF surfaceContainerLow = 0, surfaceContainer = 0, surfaceContainerHigh = 0, surfaceContainerHighest = 0;
    COLORREF onSurface = 0, onSurfaceVariant = 0, outline = 0, outlineVariant = 0;
    COLORREF primary = 0, secondaryContainer = 0, onSecondaryContainer = 0;
};

SRWLOCK g_paletteLock = SRWLOCK_INIT;
Palette g_palette;
DWORD g_paletteVersion = 0;
std::atomic<ULONGLONG> g_nextPaletteCheck{0};

struct {
    bool menus = true, scrollbars = true, statusbars = true, toolbars = true;
} g_settings;

bool ReadDword(HKEY key, const wchar_t* name, DWORD* value) {
    DWORD type = 0, size = sizeof(DWORD);
    return RegQueryValueExW(key, name, nullptr, &type, reinterpret_cast<BYTE*>(value), &size) == ERROR_SUCCESS &&
           type == REG_DWORD;
}

// The palette, re-read from the registry at most once a second (only when unidesk bumped its version).
Palette CurrentPalette() {
    ULONGLONG now = GetTickCount64();
    if (now >= g_nextPaletteCheck.load(std::memory_order_relaxed)) {
        g_nextPaletteCheck.store(now + 1000, std::memory_order_relaxed);
        HKEY key = nullptr;
        DWORD version = 0;
        if (RegOpenKeyExW(HKEY_CURRENT_USER, kPaletteKey, 0, KEY_READ, &key) == ERROR_SUCCESS) {
            ReadDword(key, L"Version", &version);
        }
        AcquireSRWLockShared(&g_paletteLock);
        bool stale = version != g_paletteVersion;
        ReleaseSRWLockShared(&g_paletteLock);
        if (stale) {
            Palette fresh;
            DWORD value = 0;
            bool complete = key != nullptr;
            auto read = [&](const wchar_t* name, COLORREF* out) {
                if (complete && ReadDword(key, name, &value)) {
                    *out = static_cast<COLORREF>(value & 0xFFFFFF);
                } else {
                    complete = false;
                }
            };
            read(L"surfaceContainerLow", &fresh.surfaceContainerLow);
            read(L"surfaceContainer", &fresh.surfaceContainer);
            read(L"surfaceContainerHigh", &fresh.surfaceContainerHigh);
            read(L"surfaceContainerHighest", &fresh.surfaceContainerHighest);
            read(L"onSurface", &fresh.onSurface);
            read(L"onSurfaceVariant", &fresh.onSurfaceVariant);
            read(L"outline", &fresh.outline);
            read(L"outlineVariant", &fresh.outlineVariant);
            read(L"primary", &fresh.primary);
            read(L"secondaryContainer", &fresh.secondaryContainer);
            read(L"onSecondaryContainer", &fresh.onSecondaryContainer);
            DWORD enabled = 0;
            fresh.enabled = complete && ReadDword(key, L"Enabled", &enabled) && enabled == 1;
            AcquireSRWLockExclusive(&g_paletteLock);
            g_palette = fresh;
            g_paletteVersion = version;
            ReleaseSRWLockExclusive(&g_paletteLock);
        }
        if (key) {
            RegCloseKey(key);
        }
    }
    AcquireSRWLockShared(&g_paletteLock);
    Palette palette = g_palette;
    ReleaseSRWLockShared(&g_paletteLock);
    return palette;
}

// ---- which control is being drawn ----------------------------------------------------------

enum class Kind { None, Menu, ScrollBar, Status, Toolbar, Rebar };

// uxtheme.dll ordinal 74: HRESULT GetThemeClass(HTHEME, LPWSTR, int). Undocumented, so
// it's checked once on start-up and the mod stays out of the way if it misbehaves.
using GetThemeClass_t = HRESULT(WINAPI*)(HTHEME, LPWSTR, int);
GetThemeClass_t g_getThemeClass = nullptr;

Kind KindOf(HTHEME theme) {
    WCHAR name[128];
    if (!theme || !g_getThemeClass || FAILED(g_getThemeClass(theme, name, ARRAYSIZE(name)))) {
        return Kind::None;
    }
    if (g_settings.menus && _wcsicmp(name, L"Menu") == 0) return Kind::Menu;
    if (g_settings.scrollbars && _wcsicmp(name, L"ScrollBar") == 0) return Kind::ScrollBar;
    if (g_settings.statusbars && _wcsicmp(name, L"Status") == 0) return Kind::Status;
    if (g_settings.toolbars && _wcsicmp(name, L"Toolbar") == 0) return Kind::Toolbar;
    if (g_settings.toolbars && _wcsicmp(name, L"Rebar") == 0) return Kind::Rebar;
    return Kind::None;
}

bool ThemeClassLookupWorks() {
    HTHEME theme = OpenThemeData(nullptr, L"Menu");
    if (!theme) {
        return false;  // no visual styles (high contrast): nothing to do
    }
    WCHAR name[64] = L"";
    HRESULT result = g_getThemeClass(theme, name, ARRAYSIZE(name));
    CloseThemeData(theme);
    return SUCCEEDED(result) && _wcsicmp(name, L"Menu") == 0;
}

// ---- drawing -------------------------------------------------------------------------------

int DpiOf(HDC hdc) {
    HWND window = WindowFromDC(hdc);
    UINT dpi = window ? GetDpiForWindow(window) : 0;
    return dpi ? static_cast<int>(dpi) : 96;
}

int Px(int value, int dpi) {
    return MulDiv(value, dpi, 96);
}

// A toolbar sitting in a rebar is on the bar this mod paints. One sitting straight on
// an app's own (often white) window keeps Windows' colours while it's at rest.
bool OnPaintedBar(HDC hdc) {
    HWND window = WindowFromDC(hdc);
    HWND parent = window ? GetParent(window) : nullptr;
    WCHAR name[32];
    return parent && GetClassNameW(parent, name, ARRAYSIZE(name)) && _wcsicmp(name, REBARCLASSNAMEW) == 0;
}

RECT Inset(const RECT& rc, int dx, int dy) {
    return {rc.left + dx, rc.top + dy, rc.right - dx, rc.bottom - dy};
}

class ClipScope {
   public:
    ClipScope(HDC hdc, const RECT* clip) : hdc_(hdc) {
        if (clip) {
            saved_ = SaveDC(hdc);
            IntersectClipRect(hdc, clip->left, clip->top, clip->right, clip->bottom);
        }
    }
    ~ClipScope() {
        if (saved_) {
            RestoreDC(hdc_, saved_);
        }
    }
    ClipScope(const ClipScope&) = delete;
    ClipScope& operator=(const ClipScope&) = delete;

   private:
    HDC hdc_;
    int saved_ = 0;
};

void Fill(HDC hdc, const RECT& rc, COLORREF color) {
    if (rc.right <= rc.left || rc.bottom <= rc.top) return;
    COLORREF previous = SetDCBrushColor(hdc, color);
    FillRect(hdc, &rc, static_cast<HBRUSH>(GetStockObject(DC_BRUSH)));
    SetDCBrushColor(hdc, previous);
}

void RoundFill(HDC hdc, const RECT& rc, COLORREF color, int radius) {
    if (rc.right <= rc.left || rc.bottom <= rc.top) return;
    COLORREF previous = SetDCBrushColor(hdc, color);
    HGDIOBJ oldBrush = SelectObject(hdc, GetStockObject(DC_BRUSH));
    HGDIOBJ oldPen = SelectObject(hdc, GetStockObject(NULL_PEN));
    // With a null pen RoundRect leaves out the right and bottom edge.
    RoundRect(hdc, rc.left, rc.top, rc.right + 1, rc.bottom + 1, radius * 2, radius * 2);
    SelectObject(hdc, oldPen);
    SelectObject(hdc, oldBrush);
    SetDCBrushColor(hdc, previous);
}

void Stroke(HDC hdc, const POINT* points, int count, COLORREF color, int width) {
    LOGBRUSH brush = {BS_SOLID, color, 0};
    HPEN pen = ExtCreatePen(PS_GEOMETRIC | PS_SOLID | PS_ENDCAP_ROUND | PS_JOIN_ROUND, std::max(1, width), &brush, 0, nullptr);
    if (!pen) return;
    HGDIOBJ oldPen = SelectObject(hdc, pen);
    Polyline(hdc, points, count);
    SelectObject(hdc, oldPen);
    DeleteObject(pen);
}

enum class Arrow { Up, Down, Left, Right };

void Chevron(HDC hdc, const RECT& rc, Arrow direction, COLORREF color, int dpi) {
    int cx = (rc.left + rc.right) / 2, cy = (rc.top + rc.bottom) / 2;
    int size = std::clamp(static_cast<int>(std::min(rc.right - rc.left, rc.bottom - rc.top)) / 4, Px(3, dpi), Px(5, dpi));
    POINT points[3];
    switch (direction) {
        case Arrow::Up:
            points[0] = {cx - size, cy + size / 2}; points[1] = {cx, cy - size / 2}; points[2] = {cx + size, cy + size / 2};
            break;
        case Arrow::Down:
            points[0] = {cx - size, cy - size / 2}; points[1] = {cx, cy + size / 2}; points[2] = {cx + size, cy - size / 2};
            break;
        case Arrow::Left:
            points[0] = {cx + size / 2, cy - size}; points[1] = {cx - size / 2, cy}; points[2] = {cx + size / 2, cy + size};
            break;
        case Arrow::Right:
            points[0] = {cx - size / 2, cy - size}; points[1] = {cx + size / 2, cy}; points[2] = {cx - size / 2, cy + size};
            break;
    }
    Stroke(hdc, points, 3, color, Px(3, dpi) / 2);
}

void CheckMark(HDC hdc, const RECT& rc, COLORREF color, int dpi) {
    int cx = (rc.left + rc.right) / 2, cy = (rc.top + rc.bottom) / 2;
    int size = std::clamp(static_cast<int>(std::min(rc.right - rc.left, rc.bottom - rc.top)) / 4, Px(3, dpi), Px(6, dpi));
    POINT points[3] = {{cx - size, cy}, {cx - size / 3, cy + size * 2 / 3}, {cx + size, cy - size * 2 / 3}};
    Stroke(hdc, points, 3, color, Px(2, dpi));
}

void Dot(HDC hdc, const RECT& rc, COLORREF color, int radius) {
    int cx = (rc.left + rc.right) / 2, cy = (rc.top + rc.bottom) / 2;
    RoundFill(hdc, {cx - radius, cy - radius, cx + radius, cy + radius}, color, radius);
}

// Hot (hovered) and open items get a rounded, Material-style highlight.
bool PaintMenu(HDC hdc, int part, int state, const RECT& rc, const Palette& p, int dpi) {
    switch (part) {
        case MENU_BARBACKGROUND:
            Fill(hdc, rc, p.surfaceContainer);
            return true;
        case MENU_BARITEM:
            Fill(hdc, rc, p.surfaceContainer);
            if (state == MBI_HOT || state == MBI_PUSHED) {
                RoundFill(hdc, Inset(rc, Px(2, dpi), Px(2, dpi)), state == MBI_PUSHED ? p.secondaryContainer : p.surfaceContainerHighest, Px(6, dpi));
            }
            return true;
        case MENU_POPUPBACKGROUND:
        case MENU_POPUPBORDERS:
        case MENU_POPUPGUTTER:
        case MENU_POPUPCHECKBACKGROUND:
            Fill(hdc, rc, p.surfaceContainerHigh);
            return true;
        case MENU_POPUPITEM:
        case 27:  // the focusable popup item newer Windows 11 builds draw
            Fill(hdc, rc, p.surfaceContainerHigh);
            if (state == MPI_HOT || state == MPI_DISABLEDHOT) {
                RoundFill(hdc, Inset(rc, Px(4, dpi), Px(1, dpi)), state == MPI_HOT ? p.secondaryContainer : p.surfaceContainerHighest, Px(6, dpi));
            }
            return true;
        case 26:  // keyboard focus outline: the highlight above already shows it
            return true;
        case MENU_POPUPSEPARATOR: {
            Fill(hdc, rc, p.surfaceContainerHigh);
            int y = (rc.top + rc.bottom) / 2;
            Fill(hdc, {rc.left + Px(10, dpi), y, rc.right - Px(10, dpi), y + std::max(1, Px(1, dpi))}, p.outlineVariant);
            return true;
        }
        case MENU_POPUPCHECK: {
            bool disabled = state == MC_CHECKMARKDISABLED || state == MC_BULLETDISABLED;
            if (state == MC_BULLETNORMAL || state == MC_BULLETDISABLED) {
                Dot(hdc, rc, disabled ? p.outline : p.primary, Px(3, dpi));
            } else {
                CheckMark(hdc, rc, disabled ? p.outline : p.primary, dpi);
            }
            return true;
        }
        case MENU_POPUPSUBMENU:
            Chevron(hdc, rc, Arrow::Right, state == MSM_DISABLED ? p.outline : p.onSurfaceVariant, dpi);
            return true;
    }
    return false;
}

bool PaintScrollBar(HDC hdc, int part, int state, const RECT& rc, const Palette& p, int dpi) {
    COLORREF track = p.surfaceContainerLow;
    switch (part) {
        case SBP_LOWERTRACKHORZ:
        case SBP_UPPERTRACKHORZ:
        case SBP_LOWERTRACKVERT:
        case SBP_UPPERTRACKVERT:
        case SBP_SIZEBOX:
            Fill(hdc, rc, track);
            return true;
        case SBP_GRIPPERHORZ:
        case SBP_GRIPPERVERT:
            return true;
        case SBP_THUMBBTNHORZ:
        case SBP_THUMBBTNVERT: {
            Fill(hdc, rc, track);
            bool vertical = part == SBP_THUMBBTNVERT;
            int thickness = vertical ? rc.right - rc.left : rc.bottom - rc.top;
            int pad = std::max(Px(2, dpi), thickness / 4);
            RECT pill = vertical ? RECT{rc.left + pad, rc.top + Px(1, dpi), rc.right - pad, rc.bottom - Px(1, dpi)}
                                 : RECT{rc.left + Px(1, dpi), rc.top + pad, rc.right - Px(1, dpi), rc.bottom - pad};
            COLORREF color = state == SCRBS_PRESSED                          ? p.primary
                             : (state == SCRBS_HOT || state == SCRBS_HOVER) ? p.outline
                                                                            : p.outlineVariant;
            int width = vertical ? pill.right - pill.left : pill.bottom - pill.top;
            RoundFill(hdc, pill, color, std::max(1, width / 2));
            return true;
        }
        case SBP_ARROWBTN: {
            Fill(hdc, rc, track);
            Arrow direction = (state <= ABS_UPDISABLED || state == ABS_UPHOVER)       ? Arrow::Up
                              : (state <= ABS_DOWNDISABLED || state == ABS_DOWNHOVER) ? Arrow::Down
                              : (state <= ABS_LEFTDISABLED || state == ABS_LEFTHOVER) ? Arrow::Left
                                                                                      : Arrow::Right;
            bool disabled = state == ABS_UPDISABLED || state == ABS_DOWNDISABLED || state == ABS_LEFTDISABLED || state == ABS_RIGHTDISABLED;
            bool active = state == ABS_UPHOT || state == ABS_UPPRESSED || state == ABS_DOWNHOT || state == ABS_DOWNPRESSED ||
                          state == ABS_LEFTHOT || state == ABS_LEFTPRESSED || state == ABS_RIGHTHOT || state == ABS_RIGHTPRESSED;
            Chevron(hdc, rc, direction, disabled ? p.outlineVariant : active ? p.onSurface : p.outline, dpi);
            return true;
        }
    }
    return false;
}

bool PaintStatus(HDC hdc, int part, const RECT& rc, const Palette& p, int dpi) {
    switch (part) {
        case 0:
        case SP_PANE:
        case SP_GRIPPERPANE:
            Fill(hdc, rc, p.surfaceContainer);
            return true;
        case SP_GRIPPER: {
            int step = Px(4, dpi), size = std::max(1, Px(2, dpi));
            for (int row = 0; row < 3; row++) {
                for (int column = 0; column <= row; column++) {
                    int x = rc.right - step * (column + 1), y = rc.bottom - step * (3 - row);
                    Fill(hdc, {x, y, x + size, y + size}, p.outline);
                }
            }
            return true;
        }
    }
    return false;
}

bool PaintRebar(HDC hdc, int part, int state, const RECT& rc, const Palette& p, int dpi) {
    switch (part) {
        case 0:
        case RP_BACKGROUND:
        case RP_BAND:
        case RP_SPLITTER:
        case RP_SPLITTERVERT:
            Fill(hdc, rc, p.surfaceContainer);
            return true;
        case RP_GRIPPER:
        case RP_GRIPPERVERT:
            return true;
        case RP_CHEVRON:
        case RP_CHEVRONVERT:
            if (state == CHEVS_HOT || state == CHEVS_PRESSED) {
                RoundFill(hdc, Inset(rc, Px(1, dpi), Px(1, dpi)), state == CHEVS_PRESSED ? p.secondaryContainer : p.surfaceContainerHighest, Px(4, dpi));
            }
            Chevron(hdc, rc, part == RP_CHEVRON ? Arrow::Right : Arrow::Down, p.onSurfaceVariant, dpi);
            return true;
    }
    return false;
}

bool PaintToolbar(HDC hdc, int part, int state, const RECT& rc, const Palette& p, int dpi) {
    switch (part) {
        case 0:
            Fill(hdc, rc, p.surfaceContainer);
            return true;
        case TP_BUTTON:
        case TP_DROPDOWNBUTTON:
        case TP_SPLITBUTTON:
        case TP_SPLITBUTTONDROPDOWN: {
            // Resting buttons stay transparent over whatever is behind them.
            bool highlighted = true;
            if (state == TS_HOT || state == TS_NEARHOT || state == TS_OTHERSIDEHOT) {
                RoundFill(hdc, Inset(rc, Px(1, dpi), Px(1, dpi)), p.surfaceContainerHighest, Px(4, dpi));
            } else if (state == TS_PRESSED || state == TS_CHECKED || state == TS_HOTCHECKED) {
                RoundFill(hdc, Inset(rc, Px(1, dpi), Px(1, dpi)), p.secondaryContainer, Px(4, dpi));
            } else {
                highlighted = false;
            }
            if (part == TP_SPLITBUTTONDROPDOWN) {
                if (!highlighted && !OnPaintedBar(hdc)) {
                    return false;  // Windows' own arrow reads well on the app's background
                }
                Chevron(hdc, rc, Arrow::Down, state == TS_DISABLED ? p.outline : p.onSurfaceVariant, dpi);
            }
            return true;
        }
        case TP_DROPDOWNBUTTONGLYPH:
            if (!OnPaintedBar(hdc)) {
                return false;
            }
            Chevron(hdc, rc, Arrow::Down, state == TS_DISABLED ? p.outline : p.onSurfaceVariant, dpi);
            return true;
        case TP_SEPARATOR: {
            int x = (rc.left + rc.right) / 2;
            Fill(hdc, {x, rc.top + Px(4, dpi), x + std::max(1, Px(1, dpi)), rc.bottom - Px(4, dpi)}, p.outlineVariant);
            return true;
        }
        case TP_SEPARATORVERT: {
            int y = (rc.top + rc.bottom) / 2;
            Fill(hdc, {rc.left + Px(4, dpi), y, rc.right - Px(4, dpi), y + std::max(1, Px(1, dpi))}, p.outlineVariant);
            return true;
        }
    }
    return false;
}

bool Paint(HTHEME theme, HDC hdc, int part, int state, const RECT* rc, const RECT* clip) {
    if (!hdc || !rc) return false;
    Kind kind = KindOf(theme);
    if (kind == Kind::None) return false;
    Palette palette = CurrentPalette();
    if (!palette.enabled) return false;
    int dpi = DpiOf(hdc);
    ClipScope scope(hdc, clip);
    switch (kind) {
        case Kind::Menu: return PaintMenu(hdc, part, state, *rc, palette, dpi);
        case Kind::ScrollBar: return PaintScrollBar(hdc, part, state, *rc, palette, dpi);
        case Kind::Status: return PaintStatus(hdc, part, *rc, palette, dpi);
        case Kind::Rebar: return PaintRebar(hdc, part, state, *rc, palette, dpi);
        case Kind::Toolbar: return PaintToolbar(hdc, part, state, *rc, palette, dpi);
        case Kind::None: break;
    }
    return false;
}

bool TextColor(HTHEME theme, HDC hdc, int part, int state, COLORREF* color) {
    Kind kind = KindOf(theme);
    if (kind == Kind::None) return false;
    Palette p = CurrentPalette();
    if (!p.enabled) return false;
    switch (kind) {
        case Kind::Menu:
            if (part == MENU_BARITEM) {
                *color = (state == MBI_HOT || state == MBI_PUSHED)                                           ? p.onSecondaryContainer
                         : (state == MBI_DISABLED || state == MBI_DISABLEDHOT || state == MBI_DISABLEDPUSHED) ? p.outline
                                                                                                             : p.onSurface;
                return true;
            }
            if (part == MENU_POPUPITEM || part == 27) {
                *color = state == MPI_HOT                                     ? p.onSecondaryContainer
                         : (state == MPI_DISABLED || state == MPI_DISABLEDHOT) ? p.outline
                                                                               : p.onSurface;
                return true;
            }
            return false;
        case Kind::Status:
            *color = p.onSurfaceVariant;
            return true;
        case Kind::Toolbar:
            if (state == TS_PRESSED || state == TS_CHECKED || state == TS_HOTCHECKED) {
                *color = p.onSecondaryContainer;
                return true;
            }
            if (state == TS_HOT || state == TS_NEARHOT || state == TS_OTHERSIDEHOT || (hdc && OnPaintedBar(hdc))) {
                *color = state == TS_DISABLED ? p.outline : p.onSurface;
                return true;
            }
            return false;  // at rest on the app's own background: its usual text colour
        case Kind::Rebar:
            *color = p.onSurface;
            return true;
        case Kind::ScrollBar:
        case Kind::None:
            break;
    }
    return false;
}

// ---- hooks ----------------------------------------------------------------------------------

decltype(&DrawThemeBackground) DrawThemeBackground_orig;
HRESULT WINAPI DrawThemeBackground_hook(HTHEME theme, HDC hdc, int part, int state, LPCRECT rect, LPCRECT clip) {
    if (Paint(theme, hdc, part, state, rect, clip)) return S_OK;
    return DrawThemeBackground_orig(theme, hdc, part, state, rect, clip);
}

decltype(&DrawThemeBackgroundEx) DrawThemeBackgroundEx_orig;
HRESULT WINAPI DrawThemeBackgroundEx_hook(HTHEME theme, HDC hdc, int part, int state, LPCRECT rect, const DTBGOPTS* options) {
    const RECT* clip = options && (options->dwFlags & DTBG_CLIPRECT) ? &options->rcClip : nullptr;
    if (Paint(theme, hdc, part, state, rect, clip)) return S_OK;
    return DrawThemeBackgroundEx_orig(theme, hdc, part, state, rect, options);
}

decltype(&DrawThemeTextEx) DrawThemeTextEx_orig;
HRESULT WINAPI DrawThemeTextEx_hook(HTHEME theme, HDC hdc, int part, int state, LPCWSTR text, int length, DWORD flags, LPRECT rect, const DTTOPTS* options) {
    COLORREF color;
    if (!TextColor(theme, hdc, part, state, &color)) {
        return DrawThemeTextEx_orig(theme, hdc, part, state, text, length, flags, rect, options);
    }
    DTTOPTS ours = {};
    if (options) {
        memcpy(&ours, options, std::min<size_t>(options->dwSize, sizeof(ours)));
    }
    ours.dwSize = sizeof(ours);
    ours.dwFlags |= DTT_TEXTCOLOR;
    ours.crText = color;
    return DrawThemeTextEx_orig(theme, hdc, part, state, text, length, flags, rect, &ours);
}

decltype(&DrawThemeText) DrawThemeText_orig;
HRESULT WINAPI DrawThemeText_hook(HTHEME theme, HDC hdc, int part, int state, LPCWSTR text, int length, DWORD flags, DWORD flags2, LPCRECT rect) {
    COLORREF color;
    if (!rect || !TextColor(theme, hdc, part, state, &color)) {
        return DrawThemeText_orig(theme, hdc, part, state, text, length, flags, flags2, rect);
    }
    DTTOPTS ours = {};
    ours.dwSize = sizeof(ours);
    ours.dwFlags = DTT_TEXTCOLOR;
    ours.crText = color;
    RECT copy = *rect;
    return DrawThemeTextEx_orig(theme, hdc, part, state, text, length, flags, &copy, &ours);
}

decltype(&GetThemeColor) GetThemeColor_orig;
HRESULT WINAPI GetThemeColor_hook(HTHEME theme, int part, int state, int property, COLORREF* color) {
    COLORREF ours;
    if (color && property == TMT_TEXTCOLOR && TextColor(theme, nullptr, part, state, &ours)) {
        *color = ours;
        return S_OK;
    }
    return GetThemeColor_orig(theme, part, state, property, color);
}

void LoadSettings() {
    g_settings.menus = Wh_GetIntSetting(L"menus") != 0;
    g_settings.scrollbars = Wh_GetIntSetting(L"scrollbars") != 0;
    g_settings.statusbars = Wh_GetIntSetting(L"statusbars") != 0;
    g_settings.toolbars = Wh_GetIntSetting(L"toolbars") != 0;
}

BOOL CALLBACK RedrawWindowOfThisProcess(HWND window, LPARAM) {
    DWORD pid = 0;
    GetWindowThreadProcessId(window, &pid);
    if (pid == GetCurrentProcessId()) {
        RedrawWindow(window, nullptr, nullptr, RDW_INVALIDATE | RDW_ERASE | RDW_FRAME | RDW_ALLCHILDREN);
    }
    return TRUE;
}

void RedrawThisProcess() {
    EnumWindows(RedrawWindowOfThisProcess, 0);
}

}  // namespace

BOOL Wh_ModInit() {
    LoadSettings();
    HMODULE uxtheme = LoadLibraryExW(L"uxtheme.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!uxtheme) {
        Wh_Log(L"uxtheme.dll isn't available");
        return FALSE;
    }
    g_getThemeClass = reinterpret_cast<GetThemeClass_t>(GetProcAddress(uxtheme, MAKEINTRESOURCEA(74)));
    if (!g_getThemeClass || !ThemeClassLookupWorks()) {
        Wh_Log(L"theme class lookup unavailable, leaving this app alone");
        return FALSE;
    }
    WindhawkUtils::SetFunctionHook(DrawThemeBackground, DrawThemeBackground_hook, &DrawThemeBackground_orig);
    WindhawkUtils::SetFunctionHook(DrawThemeBackgroundEx, DrawThemeBackgroundEx_hook, &DrawThemeBackgroundEx_orig);
    WindhawkUtils::SetFunctionHook(DrawThemeTextEx, DrawThemeTextEx_hook, &DrawThemeTextEx_orig);
    WindhawkUtils::SetFunctionHook(DrawThemeText, DrawThemeText_hook, &DrawThemeText_orig);
    WindhawkUtils::SetFunctionHook(GetThemeColor, GetThemeColor_hook, &GetThemeColor_orig);
    return TRUE;
}

void Wh_ModAfterInit() {
    RedrawThisProcess();
}

void Wh_ModUninit() {
    RedrawThisProcess();
}

void Wh_ModSettingsChanged() {
    LoadSettings();
    RedrawThisProcess();
}
