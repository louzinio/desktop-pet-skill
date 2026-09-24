"""A small Qt window with the pet in it:  python examples/qt_app.py [--cat] [--gnss] [--desktop]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "desktop-pet" / "assets" / "python"))

from desktop_pet.qt import DesktopPet, QtWidgets, QTimer, WindowPet  # noqa: E402


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    window = QtWidgets.QWidget()
    window.setWindowTitle("Desktop pet -- Qt")
    window.resize(640, 480)
    layout = QtWidgets.QVBoxLayout(window)
    layout.addWidget(QtWidgets.QLineEdit(placeholderText="Type here and it watches"))
    progress = QtWidgets.QProgressBar()
    progress.setValue(40)
    layout.addWidget(progress)
    layout.addStretch(1)
    row = QtWidgets.QHBoxLayout()
    buttons = {name: QtWidgets.QPushButton(name) for name in ("Save", "Fail", "Work")}
    for button in buttons.values():
        row.addWidget(button)
    layout.addLayout(row)
    window.show()

    kind = DesktopPet if "--desktop" in sys.argv else WindowPet
    pet = kind(window, skin="cat" if "--cat" in sys.argv else "clawd", acts="gnss" if "--gnss" in sys.argv else None)
    pet.start()
    buttons["Save"].clicked.connect(pet.pet.cheer)
    buttons["Fail"].clicked.connect(lambda: pet.pet.feel("angry", 5))

    def work() -> None:
        pet.pet.thinking = True
        QTimer.singleShot(3000, lambda: setattr(pet.pet, "thinking", False))

    buttons["Work"].clicked.connect(work)
    return app.exec() if hasattr(app, "exec") else app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
