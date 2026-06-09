"""
Phase 3: Test argos-translate German -> English translation.
Downloads the model on first run.
"""
import argostranslate.package
import argostranslate.translate
import os

# Path where argos stores models
model_dir = os.path.expanduser("~/.local/share/argos-translate/packages")

def install_de_to_en():
    """Download and install German to English translation package."""
    print("Checking for German-English translation model...")
    
    # Check if already installed
    installed = argostranslate.translate.get_installed_languages()
    for lang in installed:
        if lang.code == "de":
            for trans in lang.translations:
                if trans.code == "en":
                    print(f"  [OK] German->English model already installed: {trans}")
                    return True
    
    print("  Downloading German-English model...")
    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()
    
    de_to_en = None
    for pkg in available:
        if pkg.from_code == "de" and pkg.to_code == "en":
            de_to_en = pkg
            break
    
    if not de_to_en:
        print("  [ERR] German-English package not found in index!")
        return False
    
    print(f"  Installing translation model...")
    download_path = de_to_en.download()
    argostranslate.package.install_from_path(download_path)
    print("  [OK] German-English model installed!")
    return True


def translate(text):
    """Translate German text to English using argos-translate."""
    if not text or not text.strip():
        return text
    try:
        return argostranslate.translate.translate(text, "de", "en")
    except Exception as e:
        return f"[Translation error: {e}]"


if __name__ == "__main__":
    print("=== Phase 3: Translation Test ===")
    
    # Install model
    if not install_de_to_en():
        exit(1)
    
    # Test translations
    test_sentences = [
        "Schockanruf: Rentner übergibt 50.000 Euro in Papiertüte",
        "Gemeinderat lehnt Legehennen-Anlage für 12.000 Tiere ab",
        "Die Gemeinde Moorenweis hatte drei geplanten Windrädern das Einvernehmen verweigert.",
        "Seriendiebe in Puchheim: Mehrere Zeitungsständer aufgebrochen",
        "Volksfestplatz wird zum Park: Stadt bietet Vorab-Eindruck",
        "Nach Lkw-Brand: Mittlerer-Ring-Tunnel wochenlang dicht",
    ]
    
    print("\n--- Translation Test ---")
    for german in test_sentences:
        english = translate(german)
        print(f"\n  DE: {german}")
        print(f"  EN: {english}")
    
    print("\n=== Phase 3 complete! ===")
