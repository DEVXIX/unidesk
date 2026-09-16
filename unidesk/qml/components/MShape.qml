import QtQuick
import QtQuick.Shapes
import "../Shapes.js" as Shapes

// A filled expressive shape (cookie, flower, star, ...) sized to this item.
Shape {
    id: root
    property string shape: "cookie"
    property color color: Theme.c.primary

    preferredRendererType: Shape.CurveRenderer
    Behavior on color { ColorAnimation { duration: 500 * Theme.animationSpeed } }

    ShapePath {
        fillColor: root.color
        strokeColor: "transparent"
        strokeWidth: 0
        PathSvg { path: Shapes.path(root.shape, root.width, root.height) }
    }
}
