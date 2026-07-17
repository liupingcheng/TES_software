"""Start the virtual ADC board at the V8 DFB ADC default address."""

import sys

from virtual_adda_hardware import main


if __name__ == "__main__":
    main(["--profile", "v8-adc", *sys.argv[1:]])
