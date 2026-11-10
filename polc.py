"""
CLI compiler driver for Prototype.pol files (polc).
Translates .pol DSL files into standard .json topology definitions.

Usage:
    py -3 polc.py <input.pol> [-o <output.json>]
    py -3 polc.py --all
"""

import sys
import os
import argparse
import glob
from pol_compiler import compile_pol_file, PolCompiler


def main():
    parser = argparse.ArgumentParser(
        description="polc: TopoNet Prototype.pol Compiler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  py -3 polc.py pol_src/diamond.pol -o topology_src/diamond.json
  py -3 polc.py pol_src/star.pol -o topology_src/star.json
  py -3 polc.py --all
"""
    )
    parser.add_argument("source", nargs="?", help="Path to input .pol source file")
    parser.add_argument("-o", "--output", help="Path to destination .json file")
    parser.add_argument("-t", "--type", default="auto", help="Topology layout type (diamond, star, ring, bus, mesh, auto)")
    parser.add_argument("--all", action="store_true", help="Compile all .pol files in pol_src/ to topology_src/")
    parser.add_argument("--native", action="store_true", help="Invoke native C binary (polc.exe)")

    args = parser.parse_args()

    if args.native:
        polc_bin = "polc.exe" if os.name == "nt" else "./polc"
        if os.path.exists(polc_bin):
            pass_args = [a for a in sys.argv[1:] if a != "--native"]
            cmd = f"{polc_bin} {' '.join(pass_args)}"
            sys.exit(os.system(cmd))
        else:
            print(f"[WARN] Native binary '{polc_bin}' not found. Falling back to Python engine.")

    if args.all:
        pol_files = glob.glob(os.path.join("pol_src", "*.pol"))
        if not pol_files:
            print("No .pol files found in pol_src/")
            sys.exit(1)

        os.makedirs("topology_src", exist_ok=True)
        compiler = PolCompiler()
        success = True

        for pf in pol_files:
            base = os.path.splitext(os.path.basename(pf))[0]
            out_json = os.path.join("topology_src", f"{base}.json")
            try:
                compiler.compile_file(pf, output_path=out_json, topology_type=args.type)
                print(f"[SUCCESS] Compiled {pf} -> {out_json}")
            except Exception as e:
                print(f"[ERROR] Failed compiling {pf}: {e}")
                success = False

        sys.exit(0 if success else 1)

    if not args.source:
        parser.print_help()
        sys.exit(1)

    if not os.path.exists(args.source):
        print(f"Error: Source file '{args.source}' does not exist.")
        sys.exit(1)

    out_file = args.output
    if not out_file:
        base = os.path.splitext(args.source)[0]
        out_file = f"{base}.json"

    try:
        compiler = PolCompiler()
        compiler.compile_file(args.source, output_path=out_file, topology_type=args.type)
        print(f"[SUCCESS] Successfully compiled '{args.source}' -> '{out_file}'")
    except Exception as e:
        print(f"[ERROR] Compilation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
