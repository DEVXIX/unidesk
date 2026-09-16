.pragma library
// Material 3 expressive-style shapes as SVG paths sized to a box.
// Polar shapes: r(t) = 1 - amp + amp * cos(lobes * t), so lobes touch the box edge.

var _cache = {};

var SPECS = {
    cookie:   { lobes: 9,  amp: 0.07 },
    cookie12: { lobes: 12, amp: 0.05 },
    flower:   { lobes: 8,  amp: 0.065 },
    star:     { lobes: 8,  amp: 0.12 },
    burst:    { lobes: 12, amp: 0.09 },
    clover:   { lobes: 4,  amp: 0.16 },
    pentagon: { lobes: 5,  amp: 0.06, rot: Math.PI },
    circle:   { lobes: 0,  amp: 0 }
};

function names() { return Object.keys(SPECS).concat(["squircle", "pill"]); }

function path(name, w, h) {
    var key = name + "|" + Math.round(w) + "|" + Math.round(h);
    if (_cache[key]) return _cache[key];
    var d;
    if (name === "squircle") d = superellipse(w, h, 4.5);
    else if (name === "pill") d = superellipse(w, h, 12);
    else {
        var s = SPECS[name] || SPECS.cookie;
        d = polar(s.lobes, s.amp, s.rot || 0, w, h);
    }
    _cache[key] = d;
    return d;
}

function polar(lobes, amp, rot, w, h) {
    var n = 240, cx = w / 2, cy = h / 2, out = [];
    for (var i = 0; i < n; i++) {
        var t = i / n * Math.PI * 2;
        var r = 1 - amp + amp * Math.cos(lobes * (t + rot / Math.max(lobes, 1)));
        var x = cx + r * cx * Math.sin(t), y = cy - r * cy * Math.cos(t);
        out.push((i ? "L" : "M") + x.toFixed(2) + " " + y.toFixed(2));
    }
    return out.join(" ") + " Z";
}

function superellipse(w, h, p) {
    var n = 160, cx = w / 2, cy = h / 2, out = [];
    for (var i = 0; i < n; i++) {
        var t = i / n * Math.PI * 2, c = Math.cos(t), s = Math.sin(t);
        var x = cx + cx * Math.sign(c) * Math.pow(Math.abs(c), 2 / p);
        var y = cy + cy * Math.sign(s) * Math.pow(Math.abs(s), 2 / p);
        out.push((i ? "L" : "M") + x.toFixed(2) + " " + y.toFixed(2));
    }
    return out.join(" ") + " Z";
}

// Wavy line from x0 to x1 around y, for the seek bar.
function wave(x0, x1, y, amp, wavelength, phase) {
    if (x1 <= x0) return "M0 0";
    var out = [], step = 2;
    for (var x = x0; x <= x1; x += step) {
        out.push((x === x0 ? "M" : "L") + x.toFixed(1) + " " + (y + amp * Math.sin((x / wavelength) * Math.PI * 2 + phase)).toFixed(2));
    }
    return out.join(" ");
}
