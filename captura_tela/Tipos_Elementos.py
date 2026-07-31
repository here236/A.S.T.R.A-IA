from enum import Enum


class TipoElemento(Enum):
    BUTTON = "Button"
    EDIT = "Edit"
    TEXT = "Text"
    IMAGE = "Image"
    MENU_ITEM = "MenuItem"
    TREE_ITEM = "TreeItem"
    LINK = "Link"
    CHECK_BOX = "CheckBox"
    RADIO_BUTTON = "RadioButton"
    COMBO_BOX = "ComboBox"
    LIST = "List"
    LIST_ITEM = "ListItem"
    TAB = "Tab"
    WINDOW = "Window"