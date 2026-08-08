PAPER = "#F5EBD6"
INK = "#33243D"
OUTLINE = "#30223F"
ACCENT = "#D4A54E"
COMPLETED = "#66764F"
MUTED = "#756A68"
RULE = "#B7AA92"

TYPEWRITER_FONT = '"Courier New"'
BODY_FONT = '"Segoe UI"'


def application_stylesheet() -> str:
    return f"""
        QWidget {{
            color: {INK};
            font-family: {BODY_FONT};
            font-size: 13px;
        }}
        QLabel#projectTitle {{
            font-family: {BODY_FONT};
            font-size: 18px;
            font-weight: 700;
        }}
        QLabel#nextTask {{
            color: {MUTED};
            font-size: 11px;
        }}
        QLabel#phaseTitle {{
            font-size: 13px;
            font-weight: 700;
        }}
        QWidget#categoryHeading {{
            background: rgba(51, 36, 61, 18);
            border-radius: 6px;
        }}
        QWidget#taskRow {{
            background: rgba(255, 253, 248, 235);
            border: 1px solid rgba(51, 36, 61, 55);
            border-radius: 7px;
        }}
        QWidget#taskRow:hover {{
            background: rgba(255, 255, 255, 250);
            border: 1px solid {ACCENT};
        }}
        QToolButton {{
            background: transparent;
            border: 1px solid transparent;
            color: {INK};
            font-weight: 700;
            padding: 1px;
        }}
        QToolButton:hover, QToolButton:focus {{
            border: 1px solid {OUTLINE};
            background: rgba(212, 165, 78, 90);
        }}
        QToolButton::menu-indicator {{
            image: none;
            width: 0px;
        }}
        QProgressBar {{
            border: 1px solid {OUTLINE};
            border-radius: 5px;
            background: rgba(255, 255, 255, 180);
            height: 10px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background: {COMPLETED};
            border-radius: 4px;
        }}
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 7px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {RULE};
            min-height: 22px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QMenu {{
            background-color: {PAPER};
            border: 2px solid {OUTLINE};
            color: {INK};
            font-family: {BODY_FONT};
            font-size: 13px;
            padding: 4px;
        }}
        QMenu::item {{
            background-color: {PAPER};
            color: {INK};
            padding: 7px 28px 7px 12px;
        }}
        QMenu::item:selected {{ background-color: {ACCENT}; color: {OUTLINE}; }}
        QMenu::item:disabled {{ color: {MUTED}; }}
        QToolTip {{
            background: {PAPER};
            color: {INK};
            border: 1px solid {OUTLINE};
            padding: 4px;
        }}
    """
