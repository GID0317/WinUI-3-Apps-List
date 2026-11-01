import re
import os
import sys
import subprocess

# Ensure UTF-8 output across environments
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def get_git_added_apps(readme_path):
    """
    Finds newly added app markdown lines from the git diff (staged or HEAD changes).
    Returns a dict mapping link -> full markdown line.
    """
    diff_outputs = []
    # Try staged changes first
    try:
        out = subprocess.check_output(['git', 'diff', '--cached', '-U0', '--', readme_path], encoding='utf-8', errors='ignore')
        if out:
            diff_outputs.append(out)
    except Exception:
        pass

    # Try working tree diff
    try:
        out = subprocess.check_output(['git', 'diff', '-U0', '--', readme_path], encoding='utf-8', errors='ignore')
        if out:
            diff_outputs.append(out)
    except Exception:
        pass

    # Try last commit diff (for workflow execution on pushed commits)
    try:
        out = subprocess.check_output(['git', 'diff', 'HEAD~1', 'HEAD', '-U0', '--', readme_path], encoding='utf-8', errors='ignore')
        if out:
            diff_outputs.append(out)
    except Exception:
        pass

    added_apps = {}
    for diff in diff_outputs:
        for line in diff.splitlines():
            if line.startswith('+') and not line.startswith('+++'):
                clean = line[1:].strip()
                # Clean any logo comments
                clean = re.sub(r'\s*<!--\s*logo:\s*(https?://[^\s>]+)\s*-->', '', clean).strip()
                if clean.startswith('- ') and '](' in clean:
                    link_m = re.search(r'\[.*?\]\((https?://[^\)]+)\)', clean)
                    if link_m:
                        link = link_m.group(1).strip().lower().rstrip('/')
                        if link not in added_apps:
                            added_apps[link] = clean
    return added_apps

def sync_newly_added_apps(readme_content, git_added_apps, logo_entries):
    """
    Ensures any newly added app is present in the '## 🆕 Newly Added Apps!' section,
    sorts the section alphabetically by app name, and updates the count header.
    """
    newly_pattern = re.compile(
        r'(## 🆕 Newly Added Apps!\s*\n\s*Last )(\d+)( apps that were recently added to list!\s*\n)([\s\S]*?)(?=\n(?:<sub>.*?</sub>\s*\n\s*)?## )'
    )
    m = newly_pattern.search(readme_content)
    if not m:
        print("Warning: Could not locate '## 🆕 Newly Added Apps!' section in README.")
        return readme_content

    prefix = m.group(1)
    middle = m.group(3)
    items_block = m.group(4)

    # 1. Parse existing apps in Newly Added section
    newly_apps = {} # norm_link -> markdown_line
    for line in items_block.strip().splitlines():
        line = line.strip()
        if line.startswith('- '):
            link_m = re.search(r'\[.*?\]\((https?://[^\)]+)\)', line)
            if link_m:
                link = link_m.group(1).strip().lower().rstrip('/')
                clean_line = re.sub(r'\s*<!--\s*logo:\s*(https?://[^\s>]+)\s*-->', '', line).strip()
                newly_apps[link] = clean_line

    # 2. Check apps with logo comments in this run
    for link, line in logo_entries:
        norm_link = link.strip().lower().rstrip('/')
        if norm_link not in newly_apps:
            print(f"+ Adding to Newly Added (from logo comment): {line}")
            newly_apps[norm_link] = line

    # 3. Check apps detected from git diff
    for norm_link, line in git_added_apps.items():
        if norm_link not in newly_apps:
            print(f"+ Adding to Newly Added (from git diff): {line}")
            newly_apps[norm_link] = line

    # 4. Sort entries alphabetically by app name
    def get_app_name(line):
        name_m = re.search(r'\[(.*?)\]', line)
        return name_m.group(1).lower() if name_m else line.lower()

    sorted_lines = sorted(newly_apps.values(), key=get_app_name)
    total_count = len(sorted_lines)

    new_section_text = f"{prefix}{total_count}{middle}" + "\n".join(sorted_lines) + "\n"
    updated_content = readme_content[:m.start()] + new_section_text + readme_content[m.end():]

    print(f"✓ Synchronized Newly Added section: {total_count} apps listed.")
    return updated_content

def main():
    readme_path = 'README.md'
    output_path = 'apps_logo.yml'

    # 1. Read existing logos from apps_logo.yml (if any)
    logos = {}
    if os.path.exists(output_path):
        with open(output_path, 'r', encoding='utf-8') as f:
            yml_content = f.read()

        entry_pattern = re.compile(
            r'-\s*name:\s*"(.*?)"\s*\n\s*link:\s*"(.*?)"\s*\n\s*logo:\s*"(.*?)"',
            re.MULTILINE
        )
        for name, link, logo in entry_pattern.findall(yml_content):
            name_clean = name.replace('\\"', '"')
            logos[link.strip()] = {
                'name': name_clean,
                'logo': logo.strip()
            }

    if not os.path.exists(readme_path):
        print(f"Error: {readme_path} not found.")
        return

    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 2. Extract new logos from README.md
    extract_pattern = re.compile(
        r'(-\s*.*?\[([^\]]+)\]\((https?://[^\)]+)\).*?<!--\s*logo:\s*(https?://[^\s>]+)\s*-->)',
        re.IGNORECASE
    )
    logo_matches = extract_pattern.findall(content)

    new_logo_entries = []
    for full_line, name, link, logo in logo_matches:
        logos[link.strip()] = {
            'name': name.strip(),
            'logo': logo.strip()
        }
        clean_line = re.sub(r'\s*<!--\s*logo:\s*(https?://[^\s>]+)\s*-->', '', full_line).strip()
        new_logo_entries.append((link.strip(), clean_line))

    # 3. Detect newly added apps from git diff
    git_added = get_git_added_apps(readme_path)

    # 4. Synchronize '## 🆕 Newly Added Apps!' section & update count
    content = sync_newly_added_apps(content, git_added, new_logo_entries)

    # 5. Remove logo comments from README.md
    cleaned_content = re.sub(
        r'\s*<!--\s*logo:\s*(https?://[^\s>]+)\s*-->',
        '',
        content
    )

    # 6. Write back updated README.md
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(cleaned_content)

    # 7. Write updated apps_logo.yml
    yaml_lines = []
    sorted_logos = sorted(logos.items(), key=lambda item: item[1]['name'].lower())
    for link, data in sorted_logos:
        name_escaped = data['name'].replace('"', '\\"')
        yaml_lines.append(f'- name: "{name_escaped}"')
        yaml_lines.append(f'  link: "{link}"')
        yaml_lines.append(f'  logo: "{data["logo"]}"')

    with open(output_path, 'w', encoding='utf-8') as f:
        if yaml_lines:
            f.write('\n'.join(yaml_lines) + '\n')
        else:
            f.write('')

    print(f"Processed: Total in YML: {len(sorted_logos)}. Updated Newly Added section & cleaned README comments.")

if __name__ == '__main__':
    main()
