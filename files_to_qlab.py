import argparse
import os
import re
import subprocess

MULTI_CH_PATTERN = re.compile(
    r"^(\d)(\d{2})_(\d{3})_(\d{3})_(.+)\.(mp4|mov|m4v|png|jpg|jpeg|tga|tiff)$",
    re.IGNORECASE,
)
SINGLE_CH_PATTERN = re.compile(
    r"^(\d)(\d{2})_(\d{3})_(.+)\.(mp4|mov|m4v|png|jpg|jpeg|tga|tiff)$",
    re.IGNORECASE,
)

FADE_DURATION = 3.0


def escape_as(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def parse_media_folder(folder_path):
    cues = {}
    # os.walk recursively traverses all subfolders
    for root, _, files in os.walk(folder_path):
        for entry in files:
            full_path = os.path.join(root, entry)

            multi_match = MULTI_CH_PATTERN.match(entry)
            if multi_match:
                act, scene, scene_cue, ch, desc = (
                    int(multi_match.group(1)),
                    int(multi_match.group(2)),
                    int(multi_match.group(3)),
                    int(multi_match.group(4)),
                    multi_match.group(5).replace("_", " "),
                )
            else:
                single_match = SINGLE_CH_PATTERN.match(entry)
                if single_match:
                    act, scene, scene_cue, ch, desc = (
                        int(single_match.group(1)),
                        int(single_match.group(2)),
                        int(single_match.group(3)),
                        1,
                        single_match.group(4).replace("_", " "),
                    )
                else:
                    continue

            cues.setdefault(act, {}).setdefault(scene, {}).setdefault(
                scene_cue, []
            ).append({"channel": ch, "description": desc, "file_path": full_path})

    return cues


def generate_applescript(structured_data):
    lines = ['tell application "QLab"', "  tell front workspace"]

    global_cue_counter = 1
    prev_group_var = None

    for act in sorted(structured_data.keys()):
        lines.append('    make type "Memo"')
        lines.append("    set actMemo to last item of (selected as list)")
        lines.append('    set q number of actMemo to ""')
        lines.append(f'    set q name of actMemo to "ACT {act}"')
        lines.append("    set armed of actMemo to false")

        for scene in sorted(structured_data[act].keys()):
            lines.append('    make type "Memo"')
            lines.append("    set sceneMemo to last item of (selected as list)")
            lines.append('    set q number of sceneMemo to ""')
            lines.append(f'    set q name of sceneMemo to "Scene {act}.{scene}"')
            lines.append("    set armed of sceneMemo to false")

            for scene_cue_num in sorted(structured_data[act][scene].keys()):
                channels = sorted(
                    structured_data[act][scene][scene_cue_num],
                    key=lambda x: x["channel"],
                )
                group_name = escape_as(channels[0]["description"])
                current_cue_num = str(global_cue_counter)
                group_var = f"group_{global_cue_counter}"

                lines.append('    make type "Group"')
                lines.append(f"    set {group_var} to last item of (selected as list)")
                lines.append(f'    set q number of {group_var} to "{current_cue_num}"')
                lines.append(f'    set q name of {group_var} to "{group_name}"')
                lines.append(f"    set mode of {group_var} to timeline")

                if prev_group_var:
                    prev_num = prev_group_var.replace("group_", "")
                    lines.append('    make type "Fade"')
                    lines.append("    set fadeOut to last item of (selected as list)")
                    lines.append('    set q number of fadeOut to ""')
                    lines.append(
                        f'    set q name of fadeOut to "Fade Out Cue {prev_num}"'
                    )
                    lines.append(f"    set cue target of fadeOut to {prev_group_var}")
                    lines.append(f"    set duration of fadeOut to {FADE_DURATION}")
                    lines.append("    set do opacity of fadeOut to true")
                    lines.append("    set opacity of fadeOut to 0")
                    lines.append("    set stop target when done of fadeOut to true")
                    lines.append(
                        f"    move cue id (uniqueID of fadeOut) of parent of fadeOut to end of {group_var}"
                    )

                for ch in channels:
                    ch_desc = escape_as(ch["description"])
                    file_path = escape_as(ch["file_path"])
                    lines.append('    make type "Video"')
                    lines.append("    set vidCue to last item of (selected as list)")
                    lines.append('    set q number of vidCue to ""')
                    lines.append(
                        f'    set file target of vidCue to (POSIX file "{file_path}")'
                    )
                    lines.append(
                        f'    set q name of vidCue to "Ch {ch["channel"]} - {ch_desc}"'
                    )
                    lines.append(f'    set patch of vidCue to {ch["channel"]}')
                    lines.append("    set opacity of vidCue to 0")
                    if prev_group_var:
                        lines.append(f"    set pre wait of vidCue to {FADE_DURATION}")
                    lines.append(
                        f"    move cue id (uniqueID of vidCue) of parent of vidCue to end of {group_var}"
                    )

                lines.append('    make type "Fade"')
                lines.append("    set fadeUp to last item of (selected as list)")
                lines.append('    set q number of fadeUp to ""')
                lines.append(
                    f'    set q name of fadeUp to "Fade Up Cue {current_cue_num}"'
                )
                lines.append(f"    set cue target of fadeUp to {group_var}")
                lines.append(f"    set duration of fadeUp to {FADE_DURATION}")
                lines.append("    set do opacity of fadeUp to true")
                lines.append("    set opacity of fadeUp to 1.0")
                if prev_group_var:
                    lines.append(f"    set pre wait of fadeUp to {FADE_DURATION}")
                lines.append(
                    f"    move cue id (uniqueID of fadeUp) of parent of fadeUp to end of {group_var}"
                )

                lines.append(f"    collapse {group_var}")

                prev_group_var = group_var
                global_cue_counter += 2

    lines.append("  end tell")
    lines.append("end tell")
    return "\n".join(lines)


def build_qlab_show(folder_path):
    structured_data = parse_media_folder(folder_path)
    if not structured_data:
        print("Error: No matching media files found in directory or subdirectories.")
        return

    script = generate_applescript(structured_data)

    process = subprocess.Popen(
        ["osascript", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _, stderr = process.communicate(input=script)

    if process.returncode != 0:
        print(f"Error executing AppleScript:\n{stderr}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build QLab workspace.")
    parser.add_argument("folder", help="Path to render folder")
    args = parser.parse_args()
    build_qlab_show(os.path.abspath(args.folder))
