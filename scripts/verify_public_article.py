"""Retired privileged one-off maintenance entry point.

Use the website with the content owner's normal authenticated session. This
entry point must never load deployment secrets, mint sessions, or submit work.
"""

def main():
    raise SystemExit("Retired: use normal authenticated website actions; no work was submitted.")

if __name__ == "__main__":
    main()
