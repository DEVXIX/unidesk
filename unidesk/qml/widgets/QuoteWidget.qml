import QtQuick
import "../components"
import "../Icons.js" as Icons

// A quote a day (click for another). Your own quotes: option quotes, one per
// line as "text — author".
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property var builtIn: [
        ["Simplicity is prerequisite for reliability.", "Edsger W. Dijkstra"],
        ["Make it work, make it right, make it fast.", "Kent Beck"],
        ["The best way to predict the future is to invent it.", "Alan Kay"],
        ["Talk is cheap. Show me the code.", "Linus Torvalds"],
        ["First, solve the problem. Then, write the code.", "John Johnson"],
        ["Stay hungry, stay foolish.", "Stewart Brand"],
        ["Done is better than perfect.", "Sheryl Sandberg"],
        ["What we do in life echoes in eternity.", "Marcus Aurelius"],
        ["The obstacle is the way.", "Marcus Aurelius"],
        ["Waste no more time arguing what a good man should be. Be one.", "Marcus Aurelius"],
        ["It always seems impossible until it's done.", "Nelson Mandela"],
        ["Small daily improvements are the key to staggering long-term results.", "Unknown"],
        ["Discipline equals freedom.", "Jocko Willink"],
        ["You miss 100% of the shots you don't take.", "Wayne Gretzky"],
        ["Programs must be written for people to read, and only incidentally for machines to execute.", "Harold Abelson"],
        ["Any sufficiently advanced technology is indistinguishable from magic.", "Arthur C. Clarke"],
        ["The only way to go fast is to go well.", "Robert C. Martin"],
        ["Keep your face always toward the sunshine, and shadows will fall behind you.", "Walt Whitman"],
        ["Dream big. Start small. Act now.", "Robin Sharma"],
        ["Whether you think you can or you think you can't, you're right.", "Henry Ford"],
        ["Hard choices, easy life. Easy choices, hard life.", "Jerzy Gregorek"],
        ["The secret of getting ahead is getting started.", "Mark Twain"],
        ["Be so good they can't ignore you.", "Steve Martin"],
        ["Focus is saying no.", "Steve Jobs"],
        ["Code is like humor. When you have to explain it, it's bad.", "Cory House"],
        ["Fall seven times, stand up eight.", "Japanese proverb"],
        ["Well done is better than well said.", "Benjamin Franklin"],
        ["The future depends on what you do today.", "Mahatma Gandhi"],
        ["Quality is not an act, it is a habit.", "Aristotle"],
        ["Keep 'er steady.", "unidesk"]
    ]
    readonly property var quotes: {
        var own = String(opt("quotes", "")).split(/\r?\n/).map(function (l) { return l.trim(); }).filter(function (l) { return l; });
        if (!own.length) return builtIn;
        return own.map(function (l) { var p = l.split(/\s+[—-]\s+/); return [p[0], p[1] || ""]; });
    }
    property int offset: 0
    readonly property int dayIndex: Math.floor(new Date().setHours(0, 0, 0, 0) / 86400000)
    readonly property var q: quotes[(dayIndex + offset) % quotes.length]

    tone: opt("tone", "surface")
    implicitWidth: opt("width", 360)
    implicitHeight: body.implicitHeight + 32

    Column {
        id: body
        x: 18; y: 16
        width: parent.width - 36
        spacing: 8
        MIcon { icon: Icons.format_quote; size: 28; fill: 1; color: Theme.c.primary }
        UText {
            width: parent.width
            text: root.q[0]
            size: root.opt("font_size", 18)
            weight: Font.Medium
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            color: root.onColor
            opacity: fade.running ? 0 : 1
            Behavior on opacity { NumberAnimation { duration: 200 } }
        }
        UText { visible: root.q[1] !== ""; text: "— " + root.q[1]; size: 13; color: root.onColor; opacity: 0.7 }
    }
    Timer { id: fade; interval: 200; onTriggered: root.offset++ }
    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: fade.restart() }
}
