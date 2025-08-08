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
import os
import subprocess
import shutil
from pathlib import Path
import random


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

# -------------------------
# UTIL & DOWNLOAD HELPERS
# -------------------------

def sanitize_filename(name: str) -> str:
    safe = re.sub(r"[\\/:*?\"<>|]", " ", name)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def parse_selection_arg(arg_value: str):
    if not arg_value or str(arg_value).lower() == "all":
        return "all"
    selected: set[int] = set()
    for part in str(arg_value).split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-', 1)
            try:
                start = int(a)
                end = int(b)
            except ValueError:
                continue
            if start <= end:
                selected.update(range(start, end + 1))
            else:
                selected.update(range(end, start + 1))
        else:
            try:
                selected.add(int(part))
            except ValueError:
                continue
    return selected if selected else "all"

def ensure_ffmpeg() -> bool:
    if shutil.which("ffmpeg"):
        return True
    print(f"{Bcolors.WARNING}ffmpeg non trovato nel sistema. Provo a installarlo...{Bcolors.ENDC}")
    try:
        # Best effort install via apt-get
        subprocess.run(["bash", "-lc", "apt-get update -y && apt-get install -y ffmpeg"], check=True)
        return shutil.which("ffmpeg") is not None
    except Exception as e:
        print(f"{Bcolors.FAIL}Impossibile installare ffmpeg automaticamente: {e}{Bcolors.ENDC}")
        return False

def download_m3u8_to_mp4(m3u8_url: str, output_file: Path, referer: str = "https://flexy.stream/", user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36") -> bool:
    if not ensure_ffmpeg():
        print(f"{Bcolors.FAIL}ffmpeg non disponibile. Salto il download di: {output_file.name}{Bcolors.ENDC}")
        return False

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-user_agent", user_agent,
        "-headers", f"Referer: {referer}\r\nOrigin: {referer}",
        "-i", m3u8_url,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        str(output_file)
    ]
    try:
        print(f"{Bcolors.OKBLUE}Scarico in MP4: {output_file.name}{Bcolors.ENDC}")
        subprocess.run(cmd, check=True)
        print(f"{Bcolors.OKGREEN}Download completato: {output_file}{Bcolors.ENDC}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"{Bcolors.FAIL}Errore ffmpeg per {output_file.name}: {e}{Bcolors.ENDC}")
        return False

# -------------------------
# ESTRAZIONE M3U8 DALLA PAGINA CORRENTE
# -------------------------

def extract_m3u8_from_current_page(sb_instance: SB, is_series: bool, max_retries: int = 2) -> str | None:
    selection_iframe_selector = "iframe[src*='streaming-serie-tv']" if is_series else "iframe[src*='stream-film']"
    for attempt in range(1, max_retries + 1):
        try:
            sb_instance.wait_for_element_present(selection_iframe_selector, timeout=25)
            sb_instance.switch_to_frame(selection_iframe_selector)
            sb_instance.wait_for_ready_state_complete()

            select_element_selector = "select[name='sel_player']"
            flexy_option_value = "fx"
            sb_instance.select_option_by_value(select_element_selector, flexy_option_value)
            time.sleep(1.5)

            player_image_selector = "img[src*='player.png']"
            sb_instance.wait_for_element_present(player_image_selector, timeout=10)
            sb_instance.click(player_image_selector)

            nested_iframe_selector = "iframe[src*='uprot.net/fxe']"
            sb_instance.wait_for_element_present(nested_iframe_selector, timeout=20)
            sb_instance.switch_to_frame(nested_iframe_selector)
            sb_instance.wait_for_ready_state_complete()

            iframe_page_source = sb_instance.get_page_source()
            sb_instance.switch_to_parent_frame()
            sb_instance.switch_to_default_content()

            soup = BeautifulSoup(iframe_page_source, 'html.parser')
            for script in soup.find_all("script"):
                if "eval(function(p,a,c,k,e,d)" in script.text:
                    data_js = jsbeautifier.beautify(script.text)
                    match = re.search(r'sources:\s*\[\{\s*src:\s*"([^"]+)"', data_js)
                    if match:
                        return match.group(1)
            # Nessun link trovato nel tentativo corrente
            if attempt < max_retries:
                print(f"{Bcolors.WARNING}M3U8 non trovato, ritento ({attempt}/{max_retries})...{Bcolors.ENDC}")
                time.sleep(1.5)
        except Exception as e:
            if attempt < max_retries:
                print(f"{Bcolors.WARNING}Errore durante l'estrazione (tentativo {attempt}/{max_retries}): {e}{Bcolors.ENDC}")
                try:
                    sb_instance.switch_to_default_content()
                except Exception:
                    pass
                time.sleep(1.5)
            else:
                print(f"{Bcolors.FAIL}Estrazione fallita definitivamente: {e}{Bcolors.ENDC}")
                try:
                    sb_instance.switch_to_default_content()
                except Exception:
                    pass
    return None

# -------------------------
# ENUMERAZIONE STAGIONI/EPISODI E DOWNLOAD
# -------------------------

def get_series_title_from_page(sb_instance: SB) -> str:
    html = sb_instance.get_page_source()
    soup = BeautifulSoup(html, 'html.parser')
    h1 = soup.find('h1')
    if h1 and h1.text.strip():
        return h1.text.strip()
    title_tag = soup.find('title')
    return title_tag.text.strip() if title_tag else "Serie"

def list_clickable_children(sb_instance: SB, container_selector: str):
    elems = []
    try:
        sb_instance.wait_for_element_present(container_selector, timeout=25)
        # Proviamo diversi tipi di elementi potenzialmente cliccabili
        candidates = sb_instance.find_elements(
            f"{container_selector} a, {container_selector} button, {container_selector} li, {container_selector} div")
        for el in candidates:
            try:
                if el.is_displayed():
                    text = el.text.strip()
                    elems.append((el, text))
            except Exception:
                continue
    except Exception:
        pass
    return elems

def enumerate_and_download_series(sb_instance: SB, series_url: str, seasons_arg, episodes_arg, outdir: Path, max_retries: int = 3, delay: float = 2.0):
    print(f"{Bcolors.OKGREEN}Apro la pagina della serie: {series_url}{Bcolors.ENDC}")
    sb_instance.open(series_url)
    sb_instance.wait_for_ready_state_complete()

    series_title = sanitize_filename(get_series_title_from_page(sb_instance))
    print(f"{Bcolors.OKCYAN}Serie rilevata: {series_title}{Bcolors.ENDC}")

    # Apri l'iframe di selezione 'streaming-serie-tv' e lavora direttamente lì dentro
    try:
        selection_iframe_selector = "iframe[src*='streaming-serie-tv']"
        sb_instance.wait_for_element_present(selection_iframe_selector, timeout=25)
        player_iframe_element = sb_instance.find_element(selection_iframe_selector)
        selection_page_url = player_iframe_element.get_attribute("src")
    except Exception as e:
        print(f"{Bcolors.FAIL}Impossibile rilevare l'iframe delle stagioni/episodi: {e}{Bcolors.ENDC}")
        return

    # Apri direttamente la pagina di selezione per enumerare stagioni/episodi (come nello screenshot)
    sb_instance.open(selection_page_url)
    sb_instance.wait_for_ready_state_complete()

    def _extract_id_season_episode_from_href(href: str):
        m = re.search(r"/streaming-serie-tv/(\d+)/(\d+)/(\d+)/?", href)
        if not m:
            return None
        return m.group(1), int(m.group(2)), int(m.group(3))

    seasons_filter = parse_selection_arg(seasons_arg)
    episodes_filter = parse_selection_arg(episodes_arg)

    # Raccogli i link delle stagioni
    soup_seasons = BeautifulSoup(sb_instance.get_page_source(), 'html.parser')
    season_links = soup_seasons.select('div.div_seasons a[href*="/streaming-serie-tv/"]')

    if not season_links:
        print(f"{Bcolors.FAIL}Nessuna stagione trovata (all'interno dell'iframe di selezione).{Bcolors.ENDC}")
        return

    # Colleziona gli episodi da processare
    episodes_to_process = []
    for a in season_links:
        href = a.get('href', '')
        parsed = _extract_id_season_episode_from_href(href)
        if not parsed:
            continue
        _id, season_num, _ = parsed
        if seasons_filter != "all" and seasons_filter != "all" and isinstance(seasons_filter, set) and season_num not in seasons_filter:
            continue

        # Apri la pagina della stagione e leggi gli episodi
        sb_instance.open(href)
        sb_instance.wait_for_ready_state_complete()
        try:
            sb_instance.wait_for_element_present("div.div_episodes", timeout=20)
        except Exception:
            print(f"{Bcolors.WARNING}Impossibile trovare la lista episodi per la stagione {season_num}.{Bcolors.ENDC}")
            continue

        soup_eps = BeautifulSoup(sb_instance.get_page_source(), 'html.parser')
        ep_links = soup_eps.select('div.div_episodes a[href*="/streaming-serie-tv/"]')
        for ep_a in ep_links:
            ep_href = ep_a.get('href', '')
            parsed_ep = _extract_id_season_episode_from_href(ep_href)
            if not parsed_ep:
                continue
            _, s_num, e_num = parsed_ep
            if s_num != season_num:
                continue
            if episodes_filter != "all" and isinstance(episodes_filter, set) and e_num not in episodes_filter:
                continue
            episodes_to_process.append((s_num, e_num, ep_href))

    # Ordina e processa
    episodes_to_process.sort(key=lambda t: (t[0], t[1]))
    print(f"{Bcolors.OKBLUE}Trovati {len(episodes_to_process)} episodi totali da processare.{Bcolors.ENDC}")

    # Funzione locale per estrarre m3u8 da una pagina episodio di selezione
    def _get_m3u8_from_selection_page(selection_page_url: str) -> str | None:
        try:
            sb_instance.open(selection_page_url)
            sb_instance.wait_for_ready_state_complete()

            # Prova a selezionare il player Flexy se presente
            try:
                select_element_selector = "select[name='sel_player']"
                sb_instance.wait_for_element_present(select_element_selector, timeout=10)
                sb_instance.select_option_by_value(select_element_selector, "fx")
                time.sleep(1.2)
            except Exception:
                pass

            # Attendi direttamente l'iframe del player; evita il click sull'immagine
            nested_iframe_selector = (
                "iframe[src*='uprot.net/fxe'], "
                "iframe[src*='flexy'], "
                "iframe[src*='/fxe']"
            )
            # SeleniumBase non supporta una lista; prova vari selettori in sequenza
            nested_iframe_candidates = [
                "iframe[src*='uprot.net/fxe']",
                "iframe[src*='flexy']",
                "iframe[src*='/fxe']",
            ]
            found_selector = None
            for sel in nested_iframe_candidates:
                try:
                    sb_instance.wait_for_element_present(sel, timeout=10)
                    found_selector = sel
                    break
                except Exception:
                    continue

            # Fallback: se non trovato, prova a cliccare l'immagine del player se esiste
            if not found_selector:
                try:
                    player_image_selector = "img[src*='player.png']"
                    sb_instance.wait_for_element_present(player_image_selector, timeout=5)
                    sb_instance.click(player_image_selector)
                    # riprova a trovare l'iframe
                    for sel in nested_iframe_candidates:
                        try:
                            sb_instance.wait_for_element_present(sel, timeout=10)
                            found_selector = sel
                            break
                        except Exception:
                            continue
                except Exception:
                    pass

            if not found_selector:
                raise Exception("iframe del player non trovato")

            sb_instance.switch_to_frame(found_selector)
            sb_instance.wait_for_ready_state_complete()

            iframe_src = sb_instance.get_page_source()
            sb_instance.switch_to_default_content()

            soup_if = BeautifulSoup(iframe_src, 'html.parser')
            for script in soup_if.find_all("script"):
                if "eval(function(p,a,c,k,e,d)" in script.text:
                    data_js = jsbeautifier.beautify(script.text)
                    match = re.search(r'sources:\s*\[\{\s*src:\s*"([^"]+)"', data_js)
                    if match:
                        return match.group(1)
            return None
        except Exception as e:
            print(f"{Bcolors.WARNING}Errore durante l'estrazione dall'episodio: {e}{Bcolors.ENDC}")
            try:
                sb_instance.switch_to_default_content()
            except Exception:
                pass
            return None

    for s_num, e_num, ep_url in episodes_to_process:
        print(f"{Bcolors.OKGREEN}--> Estrazione S{s_num:02d}E{e_num:02d}{Bcolors.ENDC}")
        m3u8_link = _get_m3u8_from_selection_page(ep_url)
        if not m3u8_link:
            print(f"{Bcolors.FAIL}M3U8 non trovato per S{s_num:02d}E{e_num:02d}.{Bcolors.ENDC}")
            continue

        print(f"{Bcolors.HEADER}M3U8 trovato: {m3u8_link}{Bcolors.ENDC}")
        ensure_dir(outdir)
        out_name = f"{series_title} - Stagione {s_num:02d} - Episodio {e_num:02d}.mp4"
        out_path = outdir / sanitize_filename(out_name)
        download_m3u8_to_mp4(m3u8_link, out_path)
        time.sleep(delay + random.uniform(0.5, 1.5))


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


def main():
    """
    Funzione principale che esegue il programma.
    """
    parser = argparse.ArgumentParser(description='Cerca e scarica link .m3u8 per film e serie TV.')
    parser.add_argument('--link', type=str, help='Link diretto alla pagina del film o serie TV.')
    parser.add_argument('--seasons', type=str, default='all', help="Selezione stagioni: 'all' o lista/range es. '1,3-4'")
    parser.add_argument('--episodes', type=str, default='all', help="Selezione episodi: 'all' o lista/range es. '1,5-10'")
    parser.add_argument('--outdir', type=str, default=str(Path.cwd() / 'downloaded_files'), help='Directory di destinazione per i file MP4.')
    parser.add_argument('--headless', action='store_true', help='Esegui il browser in headless (default).')
    parser.add_argument('--no-headless', dest='headless', action='store_false', help='Mostra il browser (non headless).')
    parser.set_defaults(headless=True)
    parser.add_argument('--max-retries', type=int, default=3, help='Numero massimo di retry per estrazione m3u8.')
    parser.add_argument('--delay', type=float, default=2.0, help='Ritardo tra i download (secondi).')

    args = parser.parse_args()

    content_link = args.link
    m3u8_final_link = None

    outdir = Path(args.outdir)

    # Inizializziamo SeleniumBase in modalità Undetected-Chromedriver per bypassare Cloudflare
    with SB(uc=True, headless=args.headless, incognito=True) as sb:
        if not content_link:
            print(f"{Bcolors.OKBLUE}Benvenuto! Inserisci il nome di un film o una serie TV:{Bcolors.ENDC}")
            title = input()

            results = search_content_sb(sb, title)

            if not results:
                print(f"{Bcolors.FAIL}Nessun risultato trovato per '{title}'.{Bcolors.ENDC}")
                sys.exit()

            print("\n--- Risultati della ricerca ---")
            max_len = max(len(r['title']) for r in results) if results else 0
            name_col_width = max(max_len, len("Name"))
            type_col_width = max(len("Serie TV"), len("Type"))
            table_width = name_col_width + len("Index") + type_col_width + 8

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
            if "/serietv/" in content_link:
                enumerate_and_download_series(
                    sb_instance=sb,
                    series_url=content_link,
                    seasons_arg=args.seasons,
                    episodes_arg=args.episodes,
                    outdir=outdir,
                    max_retries=args.max_retries,
                    delay=args.delay,
                )
            else:
                # Film singolo
                m3u8_final_link = get_m3u8_link_via_seleniumbase(sb, content_link)
                if m3u8_final_link:
                    print(f"\n{Bcolors.HEADER}--- LINK .m3u8 FINALE TROVATO ---{Bcolors.ENDC}")
                    print(f"{Bcolors.OKGREEN}{m3u8_final_link}{Bcolors.ENDC}")
                    # Prova download film
                    page_title = sanitize_filename(get_series_title_from_page(sb))
                    ensure_dir(outdir)
                    out_path = outdir / f"{page_title or 'Film'}.mp4"
                    download_m3u8_to_mp4(m3u8_final_link, out_path)
                else:
                    print(f"{Bcolors.FAIL}Impossibile trovare il link .m3u8 finale.{Bcolors.ENDC}")

        print("\n--- Fine del programma ---")

if __name__ == "__main__":
    main()
