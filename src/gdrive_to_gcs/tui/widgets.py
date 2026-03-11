from __future__ import annotations

_DRIVE_ASCII_RAW = """\
                 **########=-                 
                ****#####*=---                
               *******##*------               
              **********--------              
             **********----------             
            **********  ----------            
          ***********    -----------          
          **********      ----------          
        ***********        -----------        
         #######*************++++++++         
          #####***************++++++          
           ###*****************++++           
            #*******************++            """

LOGO_WIDTH = 46  # visual character width of each logo line

_BLUE_ROW = 9  # rows >= this use blue for '#', rows < use dark-green


def _ansi_fg(hex_color: str) -> str:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"\033[38;2;{r};{g};{b}m"


_RESET      = "\033[0m"
_C_GREEN      = _ansi_fg("#1da462")  # Google Drive green  (left arm)
_C_DARK_GREEN = _ansi_fg("#0d652d")  # dark shadow at top  (green/yellow junction)
_C_YELLOW     = _ansi_fg("#fbbc04")  # Google yellow        (right arm)
_C_BLUE       = _ansi_fg("#4285f4")  # Google blue          (bottom arm)
_C_RED        = _ansi_fg("#ea4335")  # Google red           (yellow/blue junction)
_C_SHADOW     = _ansi_fg("#1a3d20")  # very dark            (centre junction)


def get_logo_lines() -> list[str]:
    """Return ANSI-colored logo lines. Each line has LOGO_WIDTH visual chars."""
    lines = _DRIVE_ASCII_RAW.split("\n")
    out = []
    for row, line in enumerate(lines):
        colored = ""
        for ch in line:
            if ch == "*":
                colored += _C_GREEN + ch + _RESET
            elif ch == "#":
                c = _C_DARK_GREEN if row < _BLUE_ROW else _C_BLUE
                colored += c + ch + _RESET
            elif ch == "-":
                colored += _C_YELLOW + ch + _RESET
            elif ch == "+":
                colored += _C_RED + ch + _RESET
            elif ch == "=":
                colored += _C_SHADOW + ch + _RESET
            else:
                colored += ch
        out.append(colored)
    return out
