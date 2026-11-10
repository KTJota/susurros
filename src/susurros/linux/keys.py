"""Key tables for Linux. Pure data: the kernel's key codes translated to the Windows virtual
key codes the rest of the app works with (shortcut filter, stored settings, key names)."""
from __future__ import annotations

KEY_ENTER, KEY_LEFTCTRL, KEY_A, KEY_V = 28, 29, 30, 47
UNMAPPED = 0x100   # keys without a Windows equivalent: 0x100 + kernel key code

# Kernel key code (linux/input-event-codes.h) -> Windows virtual key code.
_TO_VK = {
    1: 0x1B, 14: 0x08, 15: 0x09, 28: 0x0D, 57: 0x20, 58: 0x14, 69: 0x90, 70: 0x91, 99: 0x2C,
    119: 0x13, 127: 0x5D,
    # digits 1-9, 0
    2: 0x31, 3: 0x32, 4: 0x33, 5: 0x34, 6: 0x35, 7: 0x36, 8: 0x37, 9: 0x38, 10: 0x39, 11: 0x30,
    # letters, row by row
    16: 0x51, 17: 0x57, 18: 0x45, 19: 0x52, 20: 0x54, 21: 0x59, 22: 0x55, 23: 0x49, 24: 0x4F, 25: 0x50,
    30: 0x41, 31: 0x53, 32: 0x44, 33: 0x46, 34: 0x47, 35: 0x48, 36: 0x4A, 37: 0x4B, 38: 0x4C,
    44: 0x5A, 45: 0x58, 46: 0x43, 47: 0x56, 48: 0x42, 49: 0x4E, 50: 0x4D,
    # punctuation (Windows "OEM" keys)
    12: 0xBD, 13: 0xBB, 26: 0xDB, 27: 0xDD, 39: 0xBA, 40: 0xDE, 41: 0xC0, 43: 0xDC, 51: 0xBC,
    52: 0xBE, 53: 0xBF, 86: 0xE2,
    # modifiers: the Super key is the Windows key
    29: 0xA2, 97: 0xA3, 42: 0xA0, 54: 0xA1, 56: 0xA4, 100: 0xA5, 125: 0x5B, 126: 0x5C,
    # navigation
    102: 0x24, 103: 0x26, 104: 0x21, 105: 0x25, 106: 0x27, 107: 0x23, 108: 0x28, 109: 0x22,
    110: 0x2D, 111: 0x2E,
    # numeric keypad
    82: 0x60, 79: 0x61, 80: 0x62, 81: 0x63, 75: 0x64, 76: 0x65, 77: 0x66, 71: 0x67, 72: 0x68,
    73: 0x69, 55: 0x6A, 78: 0x6B, 74: 0x6D, 83: 0x6E, 98: 0x6F,
    # F1-F12
    59: 0x70, 60: 0x71, 61: 0x72, 62: 0x73, 63: 0x74, 64: 0x75, 65: 0x76, 66: 0x77, 67: 0x78,
    68: 0x79, 87: 0x7A, 88: 0x7B,
}
_TO_VK.update({183 + i: 0x7C + i for i in range(12)})   # F13-F24

# The shared key names are the Windows ones; these are what the same keys are called on Linux.
_LINUX_NAMES = {"Win": "Super", "Right Win": "Right Super"}


def to_vk(code: int) -> int:
    """The Windows virtual key code that stands for a kernel key code."""
    return _TO_VK.get(code, UNMAPPED + code)


def linux_name(name: str) -> str:
    return _LINUX_NAMES.get(name, name)
