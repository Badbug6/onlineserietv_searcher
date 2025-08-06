# Questo programma cerca film o serie TV, naviga verso la loro pagina,
# e cerca di estrarre il link .m3u8 del flusso video.
# La ricerca e la navigazione iniziale usano SeleniumBase in modalità UC.
# L'estrazione del link finale avviene analizzando direttamente la pagina del player.

# Importiamo le librerie necessarie.
from seleniumbase import SB
from bs4 import BeautifulSoup
import re
import urllib.parse
import argparse
import sys
import time
# NUOVE DIPENDENZE: Assicurati di averle installate con:
# pip install curl_cffi jsbeautifier
# La libreria curl_cffi non è più necessaria per l'estrazione finale,
# ma la manteniamo per completezza se volessi usarla altrove.
from curl_cffi import requests 
import jsbeautifier


# --- OPZIONI DI DEBUG ---
# Imposta su True per attivare la stampa dettagliata per il debug.
verbose_debug = True

# --- CONFIGURAZIONE GLOBALE ---

# Codici ANSI per i colori del testo.
class Bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Variabili globali per la configurazione del sito
BASE_URL = "https://onlineserietv.com"
SEARCH_URL = f"{BASE_URL}/?s="

# =========================================================================
# Funzioni principali per la ricerca e l'estrazione del link
# =========================================================================

def search_content_sb(sb_instance, title):
    """
    Cerca un film o una serie TV e restituisce una lista di risultati usando SeleniumBase.
    
    Args:
        sb_instance (SB): L'istanza di SeleniumBase.
        title (str): Il titolo da cercare.
        
    Returns:
        list: Una lista di dizionari con i risultati, o una lista vuota in caso di errore.
    """
    print(f"Sto cercando: {Bcolors.WARNING}{title}{Bcolors.ENDC}...")
    search_query = urllib.parse.quote_plus(title)
    url = f"{SEARCH_URL}{search_query}"
    
    try:
        sb_instance.open(url)
        # Attende i risultati o Cloudflare. Aumentato il timeout per maggiore robustezza.
        sb_instance.wait_for_element("div#box_movies", timeout=45) 
        print(f"{Bcolors.OKGREEN}Pagina dei risultati caricata con successo.{Bcolors.ENDC}")
    except Exception as e:
        print(f"{Bcolors.FAIL}Errore nella ricerca o risoluzione Cloudflare: {e}{Bcolors.ENDC}")
        page_source_on_fail = sb_instance.get_page_source()
        if "cloudflare" in page_source_on_fail.lower() or "just a moment" in page_source_on_fail.lower():
            print("Diagnosi: Sembra che Cloudflare CAPTCHA sia ancora attivo o ci sia stato un blocco.")
        return []

    page_source = sb_instance.get_page_source()
    soup = BeautifulSoup(page_source, 'html.parser')
    movie_items = soup.find_all('div', class_='movie')
    
    results = []
    for item in movie_items:
        title_tag = item.find('h2')
        link_tag = item.find('a')
        if title_tag and link_tag:
            title_text = title_tag.text.strip()
            link_url = link_tag['href']
            content_type = "Serie TV" if "/serietv/" in link_url else "Film"
            
            # Filtra i risultati per includere solo quelli che contengono il titolo cercato
            if title.lower() in title_text.lower():
                results.append({
                    'title': title_text,
                    'link': link_url,
                    'type': content_type
                })
    
    return results

# La funzione extract_m3u8_from_flexy non è più utilizzata direttamente
# perché l'analisi avviene all'interno della sessione di SeleniumBase.
# La manteniamo qui per riferimento, ma non verrà chiamata.
def extract_m3u8_from_flexy(player_url):
    """
    (NON PIÙ UTILIZZATA DIRETTAMENTE) Estrae il link .m3u8 direttamente dalla pagina del player Flexy,
    decodificando il JavaScript offuscato, usando curl_cffi.
    """
    print(f"{Bcolors.OKCYAN}Analisi diretta del player (via curl_cffi - non più il metodo principale): {player_url}{Bcolors.ENDC}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://flexy.stream/' # Un referer generico può aiutare
    }
    try:
        print(f"[*] Eseguo la richiesta al player impersonando un browser...")
        resp = requests.get(player_url, headers=headers, impersonate='chrome110', timeout=20)
        print(f"[*] Risposta del player ricevuta con status: {resp.status_code}")

        if resp.status_code != 200:
            print(f"{Bcolors.FAIL}Impossibile accedere alla pagina del player. Status: {resp.status_code}{Bcolors.ENDC}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        for script in soup.find_all("script"):
            if "eval(function(p,a,c,k,e,d)" in script.text:
                print("[*] Trovato script offuscato. Tentativo di decodifica...")
                data_js = jsbeautifier.beautify(script.text)
                match = re.search(r'sources:\s*\[\{\s*src:\s*"([^"]+)"', data_js)

                if match:
                    m3u8_link = match.group(1)
                    print(f"{Bcolors.OKGREEN}Link .m3u8 trovato nello script: {m3u8_link}{Bcolors.ENDC}")
                    return m3u8_link
        
        print(f"{Bcolors.FAIL}Nessun link .m3u8 trovato nello script offuscato.{Bcolors.ENDC}")
        return None

    except Exception as e:
        print(f"{Bcolors.FAIL}Errore durante l'analisi diretta del player: {e}{Bcolors.ENDC}")
        return None

def get_m3u8_link_via_seleniumbase(sb_instance, content_url):
    """
    Naviga alla pagina del contenuto, trova l'iframe del player di selezione,
    interagisce con esso per caricare il player Flexy (che è un iframe annidato),
    si sposta all'interno dell'iframe annidato e ne estrae il link .m3u8.
    
    Args:
        sb_instance (SB): L'istanza di SeleniumBase.
        content_url (str): L'URL della pagina del film/serie TV.
        
    Returns:
        str: Il link .m3u8, o None se non trovato.
    """
    print(f"{Bcolors.OKGREEN}Apertura del link del contenuto: {content_url}{Bcolors.ENDC}")
    sb_instance.open(content_url)
    sb_instance.wait_for_ready_state_complete() # Assicurati che la pagina principale sia caricata
    
    print(f"{Bcolors.WARNING}\n--- Ricerca del link .m3u8 ---{Bcolors.ENDC}")
    
    # Passaggio 0: Trova l'iframe del player di selezione
    selection_iframe_selector = "iframe[src*='streaming-serie-tv']" 
    try:
        print(f"{Bcolors.OKCYAN}Ricerca dell'iframe della pagina di selezione del player...{Bcolors.ENDC}")
        sb_instance.wait_for_element_present(selection_iframe_selector, timeout=20)
        
        player_iframe_element = sb_instance.find_element(selection_iframe_selector)
        player_url = player_iframe_element.get_attribute("src")
        print(f"{Bcolors.OKGREEN}URL dell'iframe di selezione trovato: {player_url}{Bcolors.ENDC}")

        # Passaggio 1: Passa al contesto dell'iframe di selezione
        print(f"{Bcolors.OKCYAN}Passaggio all'iframe di selezione per interagire con i player...{Bcolors.ENDC}")
        sb_instance.switch_to_frame(selection_iframe_selector)
        sb_instance.wait_for_ready_state_complete() # Attende che il contenuto dell'iframe sia caricato
        
        # Passaggio 2: Seleziona il player "Flexy"
        select_element_selector = "select[name='sel_player']"
        flexy_option_value = "fx"

        print(f"{Bcolors.OKCYAN}Seleziono il player '{flexy_option_value}'...{Bcolors.ENDC}")
        sb_instance.select_option_by_value(select_element_selector, flexy_option_value)
        
        # Aspettiamo un breve momento per permettere alla pagina di aggiornarsi dopo la selezione
        time.sleep(2) 

        # Passaggio 3: Clicca sull'immagine del player per avviarlo
        # L'immagine ha src="https://onlineserietv.com/player/img/player.png"
        player_image_selector = "img[src*='player.png']"
        print(f"{Bcolors.OKCYAN}Clicco sull'immagine del player per avviarlo...{Bcolors.ENDC}")
        sb_instance.wait_for_element_present(player_image_selector, timeout=10)
        sb_instance.click(player_image_selector)

        # Passaggio 4: Aspettiamo che l'iframe annidato del player effettivo sia presente
        nested_iframe_selector = "iframe[src*='uprot.net/fxe']"
        print(f"{Bcolors.OKCYAN}Attendendo il caricamento dell'iframe annidato del player Flexy...{Bcolors.ENDC}")
        sb_instance.wait_for_element_present(nested_iframe_selector, timeout=15) # Aumentato timeout
        
        # Passaggio 5: Passa al contesto dell'iframe annidato
        print(f"{Bcolors.OKCYAN}Passaggio all'iframe annidato del player Flexy per estrarre il sorgente...{Bcolors.ENDC}")
        sb_instance.switch_to_frame(nested_iframe_selector)
        sb_instance.wait_for_ready_state_complete() # Attende che il contenuto dell'iframe annidato sia caricato
        
        # Ottieni il sorgente HTML completo dell'iframe annidato
        iframe_page_source = sb_instance.get_page_source()
        
        # IMPORTANTE: Torna al frame principale DOPO aver finito con entrambi gli iframe
        # Prima torna al frame genitore dell'iframe annidato (che è il primo iframe),
        # poi torna al frame di default.
        sb_instance.switch_to_parent_frame() # Torna al primo iframe
        sb_instance.switch_to_default_content() # Torna al frame principale
        
        print(f"{Bcolors.OKCYAN}Analisi del sorgente del player Flexy (iframe annidato) per il link .m3u8...{Bcolors.ENDC}")
        soup = BeautifulSoup(iframe_page_source, 'html.parser')

        # Cerca lo script offuscato all'interno del sorgente dell'iframe annidato
        found_script = False
        for script in soup.find_all("script"):
            if "eval(function(p,a,c,k,e,d)" in script.text:
                found_script = True
                print("[*] Trovato script offuscato all'interno dell'iframe annidato. Tentativo di decodifica...")
                data_js = jsbeautifier.beautify(script.text)
                # Cerca il pattern del link .m3u8 all'interno del JavaScript decodificato
                match = re.search(r'sources:\s*\[\{\s*src:\s*"([^"]+)"', data_js)

                if match:
                    m3u8_link = match.group(1)
                    print(f"{Bcolors.OKGREEN}Link .m3u8 trovato nello script del player Flexy (iframe annidato): {m3u8_link}{Bcolors.ENDC}")
                    return m3u8_link
        
        if not found_script:
            print(f"{Bcolors.FAIL}Nessuno script offuscato con 'eval(function(p,a,c,k,e,d)' trovato nel player Flexy (iframe annidato).{Bcolors.ENDC}")
        else:
            print(f"{Bcolors.FAIL}Nessun link .m3u8 trovato nello script offuscato del player Flexy (iframe annidato) dopo la decodifica.{Bcolors.ENDC}")

        # --- DEBUG: Stampa il sorgente dell'iframe annidato se verbose_debug è True ---
        if verbose_debug:
            print(f"\n{Bcolors.WARNING}--- Sorgente HTML completo del player Flexy (iframe annidato, per debug) ---{Bcolors.ENDC}")
            print(iframe_page_source)
            print(f"{Bcolors.WARNING}----------------------------------------------------{Bcolors.ENDC}\n")
        # --------------------------------------------------------------------

        return None

    except Exception as e:
        print(f"{Bcolors.FAIL}Errore nel trovare o analizzare gli iframe del player: {e}{Bcolors.ENDC}")
        # Aggiungi un'ulteriore stampa del sorgente della pagina principale in caso di errore
        print(f"{Bcolors.WARNING}Sorgente della pagina principale al momento dell'errore (per debug):{Bcolors.ENDC}")
        # print(sb_instance.get_page_source()[:1000]) # Stampa solo i primi 1000 caratteri
        return None

def main():
    """
    Funzione principale che esegue il programma.
    """
    parser = argparse.ArgumentParser(description='Cerca e trova link .m3u8 per film e serie TV.')
    parser.add_argument('--link', type=str, help='Inserisci il link diretto alla pagina del film o serie TV.')
    args = parser.parse_args()

    content_link = args.link
    m3u8_final_link = None 

    # Inizializziamo SeleniumBase in modalità Undetected-Chromedriver per bypassare Cloudflare
    # headless=False per vedere il browser in azione, utile per il debug.
    with SB(uc=True, headless=False) as sb:
        if not content_link:
            print(f"{Bcolors.OKBLUE}Benvenuto! Inserisci il nome di un film o una serie TV:{Bcolors.ENDC}")
            title = input()
            
            results = search_content_sb(sb, title) 
            
            if not results:
                print(f"{Bcolors.FAIL}Nessun risultato trovato per '{title}'.{Bcolors.ENDC}")
                sys.exit()
                
            print("\n--- Risultati della ricerca ---")
            # Calcola le larghezze delle colonne in modo dinamico
            max_len = max(len(r['title']) for r in results) if results else 0
            name_col_width = max(max_len, len("Name"))
            type_col_width = max(len("Serie TV"), len("Type"))
            table_width = name_col_width + len("Index") + type_col_width + 8 # 8 per margini e barre
            
            print(f"{Bcolors.OKCYAN}{'-' * table_width}{Bcolors.ENDC}")
            print(f"{Bcolors.OKCYAN}| {'Index':<5} | {'Name':<{name_col_width}} | {'Type':<{type_col_width}} |{Bcolors.ENDC}")
            print(f"{Bcolors.OKCYAN}{'-' * table_width}{Bcolors.ENDC}")
            
            colors = [Bcolors.FAIL, Bcolors.OKGREEN, Bcolors.WARNING, Bcolors.OKBLUE, Bcolors.HEADER, Bcolors.OKCYAN]
            for i, result in enumerate(results):
                color = colors[i % len(colors)]
                print(f"| {color}{i+1:<5}{Bcolors.ENDC} | {color}{result['title']:<{name_col_width}}{Bcolors.ENDC} | {color}{result['type']:<{type_col_width}}{Bcolors.ENDC} |")
            print(f"{Bcolors.OKCYAN}{'-' * table_width}{Bcolors.ENDC}")

            while True:
                try:
                    selection = input(f"{Bcolors.OKBLUE}Inserisci il numero del risultato che vuoi aprire (o 'q' per uscire): {Bcolors.ENDC}")
                    if selection.lower() == 'q':
                        print("Uscita...")
                        sys.exit()
                    
                    index = int(selection) - 1
                    if 0 <= index < len(results):
                        content_link = results[index]['link']
                        break
                    else:
                        print(f"{Bcolors.FAIL}Selezione non valida. Inserisci un numero tra 1 e {len(results)}.{Bcolors.ENDC}")
                except ValueError:
                    print(f"{Bcolors.FAIL}Input non valido. Inserisci un numero.{Bcolors.ENDC}")
        
        if content_link:
            m3u8_final_link = get_m3u8_link_via_seleniumbase(sb, content_link) 
            
            if m3u8_final_link:
                print(f"\n{Bcolors.HEADER}--- LINK .m3u8 FINALE TROVATO ---{Bcolors.ENDC}")
                print(f"{Bcolors.OKGREEN}{m3u8_final_link}{Bcolors.ENDC}")
            else:
                print(f"{Bcolors.FAIL}Impossibile trovare il link .m3u8 finale.{Bcolors.ENDC}")
            
        print("\n--- Fine del programma ---")
        input(f"{Bcolors.OKBLUE}Premi Invio nel terminale per chiudere il browser...{Bcolors.ENDC}")
if __name__ == "__main__":
    main()
