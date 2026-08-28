from exporter import export_jsonl_files


if __name__ == "__main__":
    counts = export_jsonl_files()
    for name, count in counts.items():
        print(f"{name}: {count}")