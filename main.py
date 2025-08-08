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
from typing import List, Dict, Optional, Set, Tuple


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
            
            # --- QUI IL CODICE DISTINGUE TRA FILM E SERIE TV ---
            # Se l'URL contiene "/serietv/", lo classifica come "Serie TV".
            # Altrimenti, lo classifica come "Film".
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
    
    # --- MODIFICA: Determina il selettore dell'iframe in base all'URL del contenuto ---
    if "/serietv/" in content_url:
        selection_iframe_selector = "iframe[src*='streaming-serie-tv']"
        print(f"{Bcolors.OKCYAN}Identificato come Serie TV. Ricerca dell'iframe per 'streaming-serie-tv'...{Bcolors.ENDC}")
    else:
        selection_iframe_selector = "iframe[src*='stream-film']"
        print(f"{Bcolors.OKCYAN}Identificato come Film. Ricerca dell'iframe per 'stream-film'...{Bcolors.ENDC}")
    # --- FINE MODIFICA ---
    
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

# --- NUOVE FUNZIONI PER STAGIONI / EPISODI ---

def _parse_number_spec(spec: Optional[str]) -> Optional[Set[int]]:
    """Converte una stringa come "1,3-5,8" in un insieme di interi. Restituisce None se spec è None/empty."""
    if not spec:
        return None
    result: Set[int] = set()
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            try:
                start_s, end_s = part.split('-', 1)
                start, end = int(start_s), int(end_s)
                if start > end:
                    start, end = end, start
                for v in range(start, end + 1):
                    result.add(v)
            except ValueError:
                continue
        else:
            try:
                result.add(int(part))
            except ValueError:
                continue
    return result if result else None


def _extract_id_season_episode_from_href(href: str) -> Optional[Tuple[str, int, int]]:
    """Estrae (id, stagione, episodio) da href tipo /streaming-serie-tv/<id>/<season>/<episode>/"""
    m = re.search(r"/streaming-serie-tv/(\d+)/(\d+)/(\d+)/?", href)
    if not m:
        return None
    return m.group(1), int(m.group(2)), int(m.group(3))


def get_episode_links_for_series(sb_instance, series_content_url: str, seasons_spec: Optional[str], episodes_spec: Optional[str]) -> List[Dict[str, str]]:
    """
    Dato l'URL della pagina principale della serie, colleziona i link di tutti gli episodi
    in base ai filtri di stagione/episodio forniti. Ritorna una lista di dict con chiavi:
    { 'season': int, 'episode': int, 'url': str }.
    """
    print(f"{Bcolors.OKCYAN}Raccolta stagioni/episodi dalla pagina della serie...{Bcolors.ENDC}")
    seasons_filter = _parse_number_spec(seasons_spec)
    episodes_filter = _parse_number_spec(episodes_spec)

    # Apri la pagina della serie e recupera l'URL della pagina di selezione (iframe)
    sb_instance.open(series_content_url)
    sb_instance.wait_for_ready_state_complete()

    selection_iframe_selector = "iframe[src*='streaming-serie-tv']"
    sb_instance.wait_for_element_present(selection_iframe_selector, timeout=25)
    player_iframe_element = sb_instance.find_element(selection_iframe_selector)
    selection_page_url = player_iframe_element.get_attribute("src")

    # Apri direttamente la pagina di selezione per poter leggere i link
    sb_instance.open(selection_page_url)
    sb_instance.wait_for_ready_state_complete()

    episodes_to_process: List[Dict[str, str]] = []

    # Trova tutte le stagioni disponibili
    sb_instance.wait_for_element_present("div.div_seasons", timeout=20)
    seasons_source = sb_instance.get_page_source()
    soup_seasons = BeautifulSoup(seasons_source, 'html.parser')
    season_links = soup_seasons.select('div.div_seasons a[href*="/streaming-serie-tv/"]')

    if not season_links:
        print(f"{Bcolors.WARNING}Nessuna stagione trovata nella pagina di selezione.{Bcolors.ENDC}")

    for a in season_links:
        href = a.get('href', '')
        parsed = _extract_id_season_episode_from_href(href)
        if not parsed:
            continue
        _id, season_num, _episode_placeholder = parsed

        if seasons_filter is not None and season_num not in seasons_filter:
            continue

        # Apri la pagina della stagione per leggere la lista di episodi
        sb_instance.open(href)
        sb_instance.wait_for_ready_state_complete()
        try:
            sb_instance.wait_for_element_present("div.div_episodes", timeout=20)
        except Exception:
            print(f"{Bcolors.WARNING}Impossibile trovare la lista episodi per la stagione {season_num}.{Bcolors.ENDC}")
            continue

        season_page_source = sb_instance.get_page_source()
        soup_eps = BeautifulSoup(season_page_source, 'html.parser')
        ep_links = soup_eps.select('div.div_episodes a[href*="/streaming-serie-tv/"]')

        for ep_a in ep_links:
            ep_href = ep_a.get('href', '')
            parsed_ep = _extract_id_season_episode_from_href(ep_href)
            if not parsed_ep:
                continue
            _, s_num, e_num = parsed_ep
            if s_num != season_num:
                # Nel dubbio, filtra per la stagione corrente
                continue
            if episodes_filter is not None and e_num not in episodes_filter:
                continue
            episodes_to_process.append({
                'season': s_num,
                'episode': e_num,
                'url': ep_href,
            })

    # Ordina per stagione/episodio
    episodes_to_process.sort(key=lambda d: (int(d['season']), int(d['episode'])))
    print(f"{Bcolors.OKGREEN}Trovati {len(episodes_to_process)} episodi da processare.{Bcolors.ENDC}")
    return episodes_to_process


def get_m3u8_from_selection_page(sb_instance, selection_page_url: str) -> Optional[str]:
    """Apre direttamente una pagina di selezione episodio (streaming-serie-tv/ID/S/E) e restituisce il link .m3u8."""
    print(f"{Bcolors.OKGREEN}Apertura pagina episodio: {selection_page_url}{Bcolors.ENDC}")
    sb_instance.open(selection_page_url)
    sb_instance.wait_for_ready_state_complete()

    try:
        # Seleziona il player Flexy
        select_element_selector = "select[name='sel_player']"
        flexy_option_value = "fx"
        sb_instance.wait_for_element_present(select_element_selector, timeout=20)
        sb_instance.select_option_by_value(select_element_selector, flexy_option_value)
        time.sleep(2)

        # Avvia il player
        player_image_selector = "img[src*='player.png']"
        sb_instance.wait_for_element_present(player_image_selector, timeout=10)
        sb_instance.click(player_image_selector)

        # Attendi l'iframe annidato
        nested_iframe_selector = "iframe[src*='uprot.net/fxe']"
        sb_instance.wait_for_element_present(nested_iframe_selector, timeout=20)
        sb_instance.switch_to_frame(nested_iframe_selector)
        sb_instance.wait_for_ready_state_complete()

        iframe_page_source = sb_instance.get_page_source()

        # Torna al contenuto principale
        sb_instance.switch_to_default_content()

        soup = BeautifulSoup(iframe_page_source, 'html.parser')
        for script in soup.find_all("script"):
            if "eval(function(p,a,c,k,e,d)" in script.text:
                data_js = jsbeautifier.beautify(script.text)
                match = re.search(r'sources:\s*\[\{\s*src:\s*"([^"]+)"', data_js)
                if match:
                    return match.group(1)
        return None
    except Exception as e:
        print(f"{Bcolors.FAIL}Errore nell'estrazione del link dall'episodio: {e}{Bcolors.ENDC}")
        try:
            sb_instance.switch_to_default_content()
        except Exception:
            pass
        return None

def main():
    """
    Funzione principale che esegue il programma.
    """
    parser = argparse.ArgumentParser(description='Cerca e trova link .m3u8 per film e serie TV.')
    parser.add_argument('--link', type=str, help='Inserisci il link diretto alla pagina del film o serie TV.')
    # NUOVE OPZIONI per serie TV
    parser.add_argument('--all', action='store_true', help='Per serie TV: processa tutte le stagioni e gli episodi.')
    parser.add_argument('--seasons', type=str, help='Per serie TV: stagioni da includere (es. "1,3-5").')
    parser.add_argument('--episodes', type=str, help='Per serie TV: episodi da includere per ogni stagione (es. "1,2,5-8").')
    args = parser.parse_args()

    content_link = args.link
    m3u8_final_link = None 

    # Inizializziamo SeleniumBase in modalità Undetected-Chromedriver per bypassare Cloudflare
    # headless=False per vedere il browser in azione, utile per il debug.
    with SB(uc=True, headless=True) as sb:
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
        
        # Se è una serie TV e sono state richieste stagioni/episodi multipli, processa in batch
        if content_link and "/serietv/" in content_link and (args.all or args.seasons or args.episodes):
            seasons_spec = args.seasons if not args.all else None  # all ignora filtri
            episodes_spec = args.episodes if not args.all else None

            episodes = get_episode_links_for_series(sb, content_link, seasons_spec, episodes_spec)
            if not episodes:
                print(f"{Bcolors.FAIL}Nessun episodio trovato secondo i filtri specificati.{Bcolors.ENDC}")
            else:
                print(f"\n{Bcolors.HEADER}--- ESTRAZIONE LINK .m3u8 PER EPISODI ---{Bcolors.ENDC}")
                for item in episodes:
                    s = item['season']
                    e = item['episode']
                    url = item['url']
                    link = get_m3u8_from_selection_page(sb, url)
                    if link:
                        print(f"S{s:02d}E{e:02d}: {link}")
                    else:
                        print(f"S{s:02d}E{e:02d}: {Bcolors.FAIL}link non trovato{Bcolors.ENDC}")
                print(f"{Bcolors.OKBLUE}\nCompletato.{Bcolors.ENDC}")
        else:
            # Comportamento preesistente: singolo film o singolo episodio (default prima stagione/primo episodio)
            if content_link:
                m3u8_final_link = get_m3u8_link_via_seleniumbase(sb, content_link) 
                
                if m3u8_final_link:
                    print(f"\n{Bcolors.HEADER}--- LINK .m3u8 FINALE TROVATO ---{Bcolors.ENDC}")
                    print(f"{Bcolors.OKGREEN}{m3u8_final_link}{Bcolors.ENDC}")
                else:
                    print(f"{Bcolors.FAIL}Impossibile trovare il link .m3u8 finale.{Bcolors.ENDC}")
            
        print("\n--- Fine del programma ---")
        # input(f"{Bcolors.OKBLUE}Premi Invio nel terminale per chiudere il browser...{Bcolors.ENDC}")
if __name__ == "__main__":
    main()
