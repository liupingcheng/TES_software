"""Start the virtual ADC board at the reference script's fixed address."""

import sys

from virtual_adda_hardware import main


if __name__ == "__main__":
    main(["--profile", "reference-adc", *sys.argv[1:]])
