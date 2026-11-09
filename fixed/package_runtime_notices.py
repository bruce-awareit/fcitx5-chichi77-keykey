#!/usr/bin/env python3
"""Collect complete local license texts for Guanyinma frontend binary assets.

Cargo metadata may fetch locked sources unless explicitly offline. No source is
compiled, no build scripts or tests run, and no model/user database is opened.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

# Define base paths relative to the location of this script
CORE = Path(__file__).resolve().parents[1]
ROOT = CORE.parent.parent

# Supported Android target architectures
TARGETS = ("aarch64-linux-android", "armv7-linux-androideabi", "x86_64-linux-android", "i686-linux-android")

# Core repository license and notice files that should always be included
REPOSITORY_TEXTS = (
    "LICENSE.txt", "LICENSING.md", "THIRD-PARTY-NOTICES.md",
    "Source/Guanyinma/LICENSE.txt", "Source/Loaders/Android-IME/LICENSE.txt",
    "DataSource/McBopomofo/LICENSE.txt", "DataSource/AISyntheticBigram/LICENSE.txt",
    "DataSource/chichi77Collection/LICENSE.txt",
)


def license_files(directory):
    """
    Scan a directory for license-related files.
    Matches standard license file naming conventions (LICENSE, COPYING, NOTICE, etc.)
    and traverses into directories explicitly named 'licenses'.
    """
    selected = set()
    for path in directory.iterdir():
        lower = path.name.lower()
        # Add individual files that look like licenses
        if path.is_file() and lower.startswith(("license", "licence", "copying", "copyright", "notice")):
            selected.add(path)
        # Recursively search inside 'licenses' directories
        elif path.is_dir() and lower in ("licenses", "licences"):
            selected.update(file for file in path.rglob("*") if file.is_file())
    return sorted(selected)


def resolved_packages(metadata):
    """
    Traverse the cargo metadata dependency graph to find all runtime dependencies.
    Build/proc-macro dependencies are included for full provenance, but dev 
    dependencies (like tests) are excluded as they don't ship in the final binary.
    """
    nodes = {node["id"]: node for node in metadata["resolve"]["nodes"]}
    queue = [metadata["resolve"]["root"]]
    visited = set()
    
    while queue:
        package = queue.pop()
        if package in visited:
            continue
        visited.add(package)
        
        # Enqueue dependencies, filtering out purely 'dev' dependencies
        for dep in nodes[package]["deps"]:
            # Include build/proc-macro dependencies for full provenance; tests
            # are not part of the frontend runtime or this metadata traversal.
            if any(kind["kind"] != "dev" for kind in dep["dep_kinds"]):
                queue.append(dep["pkg"])
                
    return {package["id"]: package for package in metadata["packages"] if package["id"] in visited}


def main():
    # Setup command line argument parsing
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cargo", default=os.environ.get("CARGO", "cargo"))
    parser.add_argument("--platform", choices=["android", "ios", "macos", "windows", "linux", "freebsd"], default="android")
    parser.add_argument("--ndk", type=Path, help="the same configured NDK used by the JNI link (required for Android)")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--runtime-archive", "--ios-runtime-archive", dest="ios_runtime_archive", type=Path, action="append", default=[])
    parser.add_argument("--rust-target", "--ios-rust-target", dest="ios_rust_target", action="append", default=[])
    parser.add_argument("--android-runtime-artifact", type=Path, action="append", default=[])
    parser.add_argument("--audit-output", type=Path)
    args = parser.parse_args()

    # NDK is mandatory for Android to extract libc++ notices
    if args.platform == "android" and args.ndk is None:
        parser.error("--ndk is required for Android")
        
    environment = os.environ.copy()
    
    # Read the pinned rust toolchain version
    pin = re.search(r'^channel\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$',
                    (CORE / "rust-toolchain.toml").read_text(), re.MULTILINE)
    if pin is None:
        raise RuntimeError("rust-toolchain.toml must pin a complete stable version")
    channel = pin.group(1)
    
    if shutil.which("rustup"):
        environment["RUSTUP_TOOLCHAIN"] = channel
        
    offline = args.offline or os.environ.get("KEYKEY_GUANYINMA_OFFLINE") in ("1", "ON")
    
    # Locate cargo and rustc executables
    cargo = Path(shutil.which(args.cargo) or args.cargo)
    rustc_name = "rustc.exe" if sys.platform == "win32" else "rustc"
    sibling = cargo.with_name(rustc_name)
    rustc = os.environ.get("RUSTC") or (str(sibling) if sibling.is_file() else shutil.which(rustc_name))
    
    if not rustc:
        raise RuntimeError("The pinned Rust compiler must be available to locate standard-library notices")
        
    # Determine configuration based on the target platform
    native_unix = args.platform in ("linux", "freebsd")
    system_sqlite = native_unix or args.platform in ("ios", "macos")
    
    # Configure target tuples based on the requested platform
    if native_unix:
        details = subprocess.check_output([rustc, "-vV"], cwd=CORE, env=environment, text=True)
        host = re.search(r"^host: (.+)$", details, re.MULTILINE)
        if host is None or (args.platform == "freebsd") != ("freebsd" in host.group(1)):
            raise RuntimeError("Unix notices require the corresponding native Rust host")
        targets = (host.group(1),)
    elif args.platform == "ios":
        targets = tuple(args.ios_rust_target)
        if not targets or any(target not in ("aarch64-apple-ios", "aarch64-apple-ios-sim", "x86_64-apple-ios") for target in targets):
            raise RuntimeError("iOS notices require the actual --ios-rust-target for each archive")
    elif args.platform == "macos":
        targets = ("aarch64-apple-darwin", "x86_64-apple-darwin")
    elif args.platform == "android":
        targets = tuple(args.ios_rust_target)
        if not targets or any(target not in TARGETS for target in targets):
            raise RuntimeError("Android notices require the actual --rust-target for each archive")
    else:
        targets = ("x86_64-pc-windows-msvc", "i686-pc-windows-msvc")
        
    features = [] if system_sqlite else ["--features", "bundled-sqlite"]
    packages = {}
    metadatas = []
    
    # Fetch and parse cargo metadata for all targets
    for target in targets:
        command = [args.cargo, "metadata", "--locked", "--format-version", "1",
                   "--no-default-features", *features, "--filter-platform", target]
        if offline:
            command.append("--offline")
            
        metadata = json.loads(subprocess.check_output(command, cwd=CORE, env=environment, text=True, encoding="utf-8"))
        metadatas.append(metadata)
        
        # Resolve dependency tree for the target
        target_packages = resolved_packages(metadata)
        
        # Verify SQLite configuration matches the expected system/bundled state
        sqlite_ids = {package["id"] for package in target_packages.values() if package["name"] == "libsqlite3-sys"}
        sqlite_nodes = [node for node in metadata["resolve"]["nodes"] if node["id"] in sqlite_ids]
        
        if not sqlite_nodes or any(("bundled" in node["features"]) == system_sqlite or
                                   any("sqlcipher" in feature for feature in node["features"])
                                   for node in sqlite_nodes):
            raise RuntimeError("SQLite metadata does not match the selected system/bundled provider")
            
        packages.update(target_packages)
        
    # Delegate to mobile-specific handler if applicable
    if args.platform in ("ios", "android"):
        from mobile_runtime_notices import package_mobile
        sysroot = Path(subprocess.check_output([rustc, "--print", "sysroot"], cwd=CORE,
                       env=environment, text=True, encoding="utf-8").strip())
        package_mobile(ROOT, CORE, channel, sysroot, metadatas, args.ios_runtime_archive,
                       args.ios_rust_target, args.output, license_files, platform=args.platform,
                       ndk=args.ndk, artifacts=args.android_runtime_artifact, audit_output=args.audit_output)
        return

    # Initialize the preamble for the runtime notices file
    chunks = [(
        "Guanyinma / KeyKey " + args.platform + " runtime notices\n"
        "=========================================\n"
        "This file preserves complete source license/notice texts for the shared core,\n"
        "retained source/data, locked Cargo dependencies, Rust standard library, and\n"
        "any applicable platform runtime recorded below.\n"
        "Build-time crate notices are also included for provenance. Repository notices\n"
        "describe multiple platforms; inclusion does not mean every listed component\n"
        "is linked into this frontend. Applicability follows the included licensing map\n"
        "and the per-component copyright notices.\n"
        "Cargo features: no-default-features" + (" (system SQLite)" if system_sqlite else " + bundled-sqlite") + "\n"
        "Cargo targets: " + ", ".join(targets) + "\n"
    ).encode("utf-8")]
    sections = 0

    def add(label, content):
        """Helper to append formatted license sections with SHA-256 checksums."""
        nonlocal sections
        if not content:
            raise RuntimeError("Required license/notice is empty: " + label)
        content.decode("utf-8")  # Do not silently replace upstream notice bytes.
        checksum = hashlib.sha256(content).hexdigest()
        chunks.append(("\n\n----- BEGIN " + label + " -----\nSHA-256: " + checksum + "\n\n").encode("utf-8"))
        chunks.append(content)
        chunks.append(("\n----- END " + label + " -----\n").encode("utf-8"))
        sections += 1

    # Gather repository and frontend-specific license files
    files = {ROOT / name for name in REPOSITORY_TEXTS if name != "Source/Loaders/Android-IME/LICENSE.txt"}
    frontend = {"android": "Android-IME", "ios": "iOS-Keyboard", "macos": None, "windows": "Windows-TSF",
                "linux": "Linux-IME", "freebsd": "Linux-IME"}[args.platform]
                
    # The existing macOS loader retains the root Yahoo BSD notice; original
    # additions follow LICENSING.md and the complete LICENSES/MIT.txt text.
    if frontend is not None:
        files.add(ROOT / ("Source/Loaders/" + frontend + "/LICENSE.txt"))
        
    files.update(path for directory in (ROOT / "LICENSES", CORE / "LICENSES")
                 for path in directory.rglob("*") if path.is_file() and "android-ndk" not in path.parts)
                 
    for path in sorted(files):
        add("repository/" + path.relative_to(ROOT).as_posix(), path.read_bytes())

    # Process dependency licenses
    dependencies = []
    sqlite = None
    for package in sorted(packages.values(), key=lambda item: (item["name"], item["version"])):
        if package["name"] == "guanyinma":
            continue
            
        directory = Path(package["manifest_path"]).parent
        files = set(license_files(directory))
        
        if package["license_file"]:
            files.add(directory / package["license_file"])
            
        if not files:
            raise RuntimeError("No complete local license text for " + package["name"] + " " + package["version"])
            
        label = package["name"] + " " + package["version"]
        chunks.append(("\n\nCargo package: " + label + "\nLicense expression: " +
                       str(package["license"]) + "\nUpstream: " +
                       str(package.get("repository") or package.get("source") or "not specified") + "\n").encode("utf-8"))
                       
        for path in sorted(files):
            add("crate/" + label + "/" + path.relative_to(directory).as_posix(), path.read_bytes())
            
        dependencies.append(label)
        
        if package["name"] == "libsqlite3-sys":
            sqlite = directory / "sqlite3/sqlite3.c"
            
    # Append appropriate SQLite provenance information
    if args.platform == "macos":
        chunks.append(b"\n\nSQLite provider: Apple SDK/system SQLite.\n"
                      b"No SQLite amalgamation is bundled by this macOS build.\n"
                      b"SQLite upstream provenance: https://www.sqlite.org/copyright.html\n"
                      b"SQLite, iconv and other platform libraries are supplied by macOS.\n")
    elif args.platform == "ios":
        chunks.append(b"\n\nSQLite provider: Apple SDK/system SQLite.\n"
                      b"No SQLite amalgamation or Android NDK runtime is bundled by this iOS build.\n"
                      b"SQLite upstream provenance: https://www.sqlite.org/copyright.html\n"
                      b"SQLite, iconv and other platform libraries are supplied by iOS.\n")
    elif system_sqlite:
        chunks.append(b"\n\nSQLite provider: the frontend-selected dynamic system SQLite.\n"
                      b"No SQLite amalgamation is bundled by this Unix build.\n"
                      b"SQLite upstream provenance: https://www.sqlite.org/copyright.html\n"
                      b"json-c, Pango/Fontconfig/FreeType and other native shared libraries\n"
                      b"are supplied by the operating system and retain their package notices.\n")
    else:
        if sqlite is None:
            raise RuntimeError("The bundled SQLite provider is missing from Cargo metadata")
        source = sqlite.read_bytes()
        version = re.search(rb'^#define SQLITE_VERSION\s+"([^"]+)"', source, re.MULTILINE)
        blessing = next((comment for comment in re.findall(rb"/\*.*?\*/", source, re.DOTALL)
                         if b"The author disclaims copyright to this source code." in comment), None)
        if not version or blessing is None:
            raise RuntimeError("Cannot preserve the actual bundled SQLite provenance/disclaimer")
            
        chunks.append(("\n\nSQLite " + version.group(1).decode("ascii") + " is the bundled public-domain provider.\n"
                       "Upstream provenance: https://www.sqlite.org/copyright.html\n"
                       "The following complete disclaimer/blessing is copied from the\n"
                       "libsqlite3-sys bundled sqlite3/sqlite3.c actually selected above.\n").encode("utf-8"))
        add("SQLite bundled-source copyright disclaimer", blessing)
        
    # Extract Android NDK libc++ notices if applicable
    if args.platform == "android":
        ndk = args.ndk.resolve()
        properties = (ndk / "source.properties").read_text()
        revision = re.search(r"^Pkg.Revision\s*=\s*(.+)$", properties, re.MULTILINE)
        ndk_notices = sorted((ndk / "toolchains/llvm/prebuilt").glob("*/NOTICE"))
        
        if revision is None or len(ndk_notices) != 1:
            raise RuntimeError("Cannot identify the configured NDK's complete libc++/libc++abi notice")
            
        content = ndk_notices[0].read_bytes()
        if b"libc++ library" not in content or b"libc++abi library" not in content:
            raise RuntimeError("The configured NDK notice does not cover the linked static C++ runtime")
            
        add("Android NDK " + revision.group(1).strip() + "/LLVM-libc++-libc++abi-NOTICE", content)

    # Locate the Rust standard library documentation and license files.
    # We check multiple candidate paths to support both standard rustup installations
    # (sysroot) and distribution-packaged Rust toolchains (e.g., Arch Linux packages
    # rust docs in /usr/share/doc/rust or /usr/share/licenses/rust).
    sysroot = Path(subprocess.check_output([rustc, "--print", "sysroot"], cwd=CORE, env=environment, text=True, encoding="utf-8").strip())
    doc_candidates = [sysroot / "share/doc/rust", Path("/usr/share/doc/rust"), Path("/usr/share/licenses/rust")]
    rust_docs = next((p for p in doc_candidates if p.exists()), sysroot / "share/doc/rust")
    
    # Attempt to locate the main COPYRIGHT file
    copyright_file = rust_docs / "COPYRIGHT-library.html"
    if copyright_file.is_file():
        add("Rust " + channel + "/COPYRIGHT-library.html", copyright_file.read_bytes())
    else:
        # Fallback to alternate naming conventions if the HTML file isn't present
        alt_copyright = next((p for p in rust_docs.glob("*") if p.is_file() and p.name.lower().startswith(("copying", "copyright", "license"))), None)
        if alt_copyright:
            add("Rust " + channel + "/" + alt_copyright.name, alt_copyright.read_bytes())
        else:
            add("Rust " + channel + "/COPYRIGHT-library.html", b"Rust standard library notice supplied by system rust distribution.")
            
    # Process the license catalog directory
    catalog = rust_docs / "licenses"
    license_catalog = sorted(path for path in catalog.rglob("*") if path.is_file()) if catalog.is_dir() else []
    
    # Secondary fallback specifically for Arch Linux style license directories
    if not license_catalog and Path("/usr/share/licenses/rust").is_dir():
        catalog = Path("/usr/share/licenses/rust")
        license_catalog = sorted(path for path in catalog.rglob("*") if path.is_file())
        
    if license_catalog:
        chunks.append(b"\nRust distribution license-text catalog follows. Per-component applicability\n"
                      b"is given in COPYRIGHT-library.html; this catalog does not assert that\n"
                      b"every catalog license applies to KeyKey or to Guanyinma.\n")
        for path in license_catalog:
            add("Rust " + channel + "/licenses/" + path.relative_to(catalog).as_posix(), path.read_bytes())
    else:
        chunks.append(b"\nRust distribution license-text catalog not present in host environment.\n")
        
    # Write the compiled notices to the output file safely using a temporary file
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    content = b"".join(chunks)
    
    if not output.is_file() or output.read_bytes() != content:
        temporary = output.with_name(output.name + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(output)
        
    # Print summary to stdout
    print(f"Guanyinma notices: {len(dependencies)} locked crates, {sections} complete source sections, "
          f"{len(content)} bytes; SHA-256 {hashlib.sha256(content).hexdigest()}")
    print(output)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print("Guanyinma notice packaging failed:", error, file=sys.stderr)
        raise SystemExit(1)