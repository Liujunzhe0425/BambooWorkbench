from pathlib import Path
from xml.etree import ElementTree

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


def _alpha_bounds(
    image: QImage,
    left: int,
    right: int,
    top: int = 0,
    bottom: int | None = None,
) -> tuple[int, int, int, int]:
    bottom = image.height() if bottom is None else bottom
    pixels = [
        (x, y)
        for y in range(top, bottom)
        for x in range(left, right)
        if image.pixelColor(x, y).alpha() > 0
    ]
    assert pixels
    xs, ys = zip(*pixels, strict=True)
    return min(xs), min(ys), max(xs), max(ys)


def test_team_logo_is_self_contained_svg_with_approved_identity(qapp) -> None:
    logo_path = Path(__file__).parents[2] / "assets" / "brand" / "team-logo.svg"
    root = ElementTree.parse(logo_path).getroot()
    source = logo_path.read_text(encoding="utf-8")
    elements = list(root.iter())
    title = next(element for element in elements if element.tag.endswith("title"))
    description = next(element for element in elements if element.tag.endswith("desc"))

    assert root.tag.endswith("svg")
    assert title.text == "湖大智竹实践团队"
    assert "湖大智竹实践团队" in description.text
    assert "#2FA47D" in source
    assert "#294D3C" in source
    assert not any(element.tag.endswith(("image", "text")) for element in elements)
    assert "href=" not in source
    assert "font-family" not in source
    assert QPixmap(str(logo_path)).isNull() is False

    image = QImage(150, 54, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(str(logo_path))
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, 150, 54))
    painter.end()
    symbol_bounds = _alpha_bounds(image, 0, 40)
    lettering_bounds = _alpha_bounds(image, 42, 150, 20, 37)
    assert symbol_bounds[2] < lettering_bounds[0]
    assert all(
        image.pixelColor(x, y).alpha() == 0
        for x in (40, 41)
        for y in range(image.height())
    )
