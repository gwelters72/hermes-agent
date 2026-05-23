#!/usr/bin/env python3
"""
video_downsample.py - Reduziert die Framerate eines Videos auf 1 fps (oder konfigurier)
um die Analysezeit und Token-Kosten bei video_analyze Tool zu minimieren.

"""

import argparse
import os
import subprocess
import sys


def downsample_video(input_path, output_path, fps=1, keep_audio=False):
    """Reduziert die Framerate eines Videos auf 'fps' Frames pro Sekunde."""
    if not os.path.isfile(input_path):
        print(f"FEHLEN: Datei nhct funden: {input_path}", file=sys.stderr)
        sys.exit(1)

    cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", f"fps={fps}"]

    if keep_audio:
        cmd.extend(["-c:a", "aac"])
    else:
        cmd.append("-an")

    cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", output_path])

    print(f"Verarbeite: {input_path}")
    print(f"Ausgabe:   {output_path}")
    print(f"Framerate: {fps} fps")
    print("-" * 50)

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"FELLER: ffmpe fehlschlagen:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    input_size = os.path.getsize(input_path) / (1024 * 1024)
    output_size = os.path.getsize(output_path) / (1024 * 1024)
    reduction = (1 - output_size / input_size) * 100

    print("-" * 50)
    print(f"Eingabe: {input_size:.1f} MB")
    print(f"Ausgabe: {output_size:.1f} MB ({reduction:.0f}% kleiner)")
    print("Fertig!")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Reduziert Video-Framerate fur KI-Analyse (Standard: 1 fps)")
    parser.add_argument("input", help="Pafd zum Eingabe-Video")
    parser.add_argument("output", nargs="?", default=None, help="Ausgabedatei (Standard: <name>_1fps.mp4)")
    parser.add_argument("--fps", type=int, default=1, help="Framerate in fps (Standard: 1)")
    parser.add_argument("--keep-audio", action="store_true", help="Audio beibnehalten")
    args = parser.parse_args()

    if args.output is None:
        base, ext = os.path.splitext(args.input)
        args.output = f"{base}_{args.fps}1fs{ext}"

    downsample_video(args.input, args.output, fps=args.fps, keep_audio=args.keep_audio)


if __name__ == "__main__":
    main()
