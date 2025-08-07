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
import subprocess
import os
import signal

# NUOVE DIPENDENZE: Assicurati di averle installate con:
# pip install jsbeautifier tqdm
# E che 'ffmpeg' e 'ffprobe' siano nel tuo PATH.
import jsbeautifier
from tqdm import tqdm

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
    
    # Determina il selettore dell'iframe in base all'URL del contenuto
    if "/serietv/" in content_url:
        selection_iframe_selector = "iframe[src*='streaming-serie-tv']"
        print(f"{Bcolors.OKCYAN}Identificato come Serie TV. Ricerca dell'iframe per 'streaming-serie-tv'...{Bcolors.ENDC}")
    else:
        selection_iframe_selector = "iframe[src*='stream-film']"
        print(f"{Bcolors.OKCYAN}Identificato come Film. Ricerca dell'iframe per 'stream-film'...{Bcolors.ENDC}")
    
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

class HLS_Downloader:
    """
    Una classe per scaricare e convertire un flusso HLS (.m3u8) in un file .mp4
    usando ffmpeg.
    """
    def __init__(self, m3u8_url, output_path):
        self.m3u8_url = m3u8_url
        self.output_path = output_path
        
    def start(self):
        # Aggiunge l'estensione .mp4 se non è già presente
        if not self.output_path.lower().endswith(".mp4"):
            self.output_path += ".mp4"
        
        # Crea la cartella "Download" se non esiste
        download_folder = "Download"
        if not os.path.exists(download_folder):
            os.makedirs(download_folder)

        full_output_path = os.path.join(download_folder, self.output_path)

        # Verifica se il file di destinazione esiste già
        if os.path.exists(full_output_path):
            print(f"{Bcolors.WARNING}Il file '{full_output_path}' esiste già. Saltando il download.{Bcolors.ENDC}")
            return {'error': None, 'output_path': full_output_path}
            
        print(f"\n{Bcolors.OKCYAN}" + "="*70 + Bcolors.ENDC)
        print(f"{Bcolors.OKCYAN}Download: {Bcolors.OKGREEN}{os.path.basename(full_output_path)}{Bcolors.ENDC}")
        print(f"{Bcolors.OKCYAN}Puoi fermare il download premendo {Bcolors.WARNING}Ctrl+C{Bcolors.ENDC}{Bcolors.OKCYAN}{Bcolors.ENDC}")
        print(f"{Bcolors.OKCYAN}" + "="*70 + Bcolors.ENDC)

        try:
            # Step 1: Usa ffprobe per ottenere la durata totale del video in modo affidabile
            print(f"{Bcolors.OKCYAN}Determinazione della durata del video con ffprobe...{Bcolors.ENDC}")
            probe_command = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", self.m3u8_url]
            try:
                probe_output = subprocess.check_output(probe_command, universal_newlines=True, stderr=subprocess.STDOUT, timeout=10)
                total_duration_seconds = float(probe_output.strip()) if probe_output.strip() else None
            except subprocess.TimeoutExpired:
                print(f"{Bcolors.WARNING}Timeout scaduto per ffprobe. Proseguo senza durata totale.{Bcolors.ENDC}")
                total_duration_seconds = None
            except (subprocess.CalledProcessError, ValueError) as e:
                print(f"{Bcolors.FAIL}Errore nell'esecuzione di ffprobe: {e}. Proseguo senza durata totale.{Bcolors.ENDC}")
                total_duration_seconds = None
            
            if total_duration_seconds:
                # Calcola ore, minuti e secondi
                hours = int(total_duration_seconds / 3600)
                minutes = int((total_duration_seconds % 3600) / 60)
                seconds = total_duration_seconds % 60
                
                print(f"{Bcolors.OKGREEN}Durata totale del video: {hours}h {minutes}m {seconds:.2f}s.{Bcolors.ENDC}")

            # Step 2: Prepara il comando ffmpeg per il download effettivo
            ffmpeg_command = [
                "ffmpeg",
                "-i", self.m3u8_url,
                "-c", "copy",
                "-bsf:a", "aac_adtstoasc",
                full_output_path
            ]
            
            process = subprocess.Popen(
                ffmpeg_command,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Inizializza le variabili per il calcolo della velocità (non più necessario)
            
            # Step 3: Gestisci la barra di progressione con tqdm
            total = total_duration_seconds if total_duration_seconds else 100
            unit = "s" if total_duration_seconds else "%"
            
            with tqdm(total=total, unit=unit, dynamic_ncols=True, leave=True,
                      desc=f"{Bcolors.OKGREEN}[Download]{Bcolors.ENDC}",
                      bar_format="{desc}: {percentage:3.0f}%|{bar}{postfix}",
                      colour='green',
                      miniters=1) as pbar:

                for line in iter(process.stderr.readline, ''):
                    # Rimuovi l'output di debug di ffmpeg
                    # if verbose_debug:
                    #     print(f"[DEBUG FFMPEG] {line.strip()}")
                        
                    # Modifiche per una migliore robustezza
                    match_time = re.search(r"time=(\d{2}):(\d{2}):(\d{2})\.\d+", line)
                    match_size = re.search(r"size=\s*(\d+)(\w+)", line) # Cattura anche l'unità (kB, MB, etc.)
                    
                    current_size_kb = None
                    current_time_seconds = None
                    
                    if match_time:
                        h, m, s = match_time.groups()
                        current_time_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                        
                        if total_duration_seconds:
                            pbar.update(current_time_seconds - pbar.n)
                            
                    if match_size:
                        size_value = int(match_size.group(1))
                        size_unit = match_size.group(2)
                        
                        # Converte la dimensione in KB per un calcolo coerente
                        if size_unit == 'kB':
                            current_size_kb = size_value
                        elif size_unit == 'MB':
                            current_size_kb = size_value * 1024
                        elif size_unit == 'GB':
                            current_size_kb = size_value * 1024 * 1024

                    postfix_str = ""
                    if current_size_kb is not None:
                        current_size_mb_display = current_size_kb / 1024
                        postfix_str += f" | {Bcolors.OKCYAN}Size: {Bcolors.WARNING}{current_size_mb_display:.2f}MB{Bcolors.ENDC}"
                    
                    if postfix_str:
                        pbar.set_postfix_str(postfix_str)

            # Aspetta che il processo termini e ottiene il codice di ritorno
            process.wait()

            if process.returncode == 0:
                print(f"\n\n{Bcolors.OKGREEN}Download e conversione completati con successo!{Bcolors.ENDC}")
                return {'error': None, 'output_path': full_output_path}
            else:
                print(f"\n\n{Bcolors.FAIL}Errore: ffmpeg ha terminato con il codice {process.returncode}{Bcolors.ENDC}")
                return {'error': f"ffmpeg error code: {process.returncode}", 'output_path': None}

        except FileNotFoundError:
            print(f"\n{Bcolors.FAIL}Errore: 'ffmpeg' o 'ffprobe' non trovato. Assicurati che siano installati e nel tuo PATH.{Bcolors.ENDC}")
            return {'error': "ffmpeg or ffprobe not found", 'output_path': None}
        except Exception as e:
            print(f"\n{Bcolors.FAIL}Si è verificato un errore inaspettato: {e}{Bcolors.ENDC}")
            return {'error': f"unexpected error: {e}", 'output_path': None}
        
def main():
    """
    Funzione principale che esegue il programma.
    """
    parser = argparse.ArgumentParser(description='Cerca e trova link .m3u8 per film e serie TV.')
    parser.add_argument('--link', type=str, help='Inserisci il link diretto alla pagina del film o serie TV.')
    # Aggiungi un nuovo argomento per il link m3u8 diretto
    parser.add_argument('-l', '--m3u8-link', type=str, help='Inserisci direttamente il link .m3u8 per avviare il download.')
    args = parser.parse_args()

    # Prendi il link m3u8 dal nuovo argomento, se fornito
    m3u8_final_link = args.m3u8_link
    content_link = args.link
    results = None

    # Inizializziamo SeleniumBase solo se necessario (se non è stato fornito un link m3u8)
    if not m3u8_final_link:
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
            
            if content_link:
                m3u8_final_link = get_m3u8_link_via_seleniumbase(sb, content_link) 
    
    # Se un link m3u8 è stato trovato o fornito, avvia il download
    if m3u8_final_link:
        print(f"\n{Bcolors.HEADER}--- LINK .m3u8 FINALE TROVATO ---{Bcolors.ENDC}")
        print(f"{Bcolors.OKGREEN}{m3u8_final_link}{Bcolors.ENDC}")

        # Chiede all'utente se vuole scaricare
        download_choice = input(f"{Bcolors.OKBLUE}Vuoi scaricare il video in formato .mp4? (s/n): {Bcolors.ENDC}")
        if download_choice.lower() == 's':
            filename_suggestion = "video_scaricato"
            if results and 'index' in locals():
                filename_suggestion = results[index]['title'].replace(" ", "_").replace(":", "").replace("/", "")
            
            output_filename = input(f"{Bcolors.OKBLUE}Inserisci il nome del file di output (es. {filename_suggestion}.mp4): {Bcolors.ENDC}")
            
            if output_filename:
                # Qui chiamiamo la nuova classe HLS_Downloader
                downloader = HLS_Downloader(m3u8_url=m3u8_final_link, output_path=output_filename)
                result = downloader.start()

                if result['error']:
                    print(f"{Bcolors.FAIL}Il download ha fallito: {result['error']}{Bcolors.ENDC}")
                else:
                    print(f"{Bcolors.OKGREEN}File salvato in: {result['output_path']}{Bcolors.ENDC}")
            else:
                print(f"{Bcolors.WARNING}Nome file non inserito, operazione annullata.{Bcolors.ENDC}")
    else:
        print(f"{Bcolors.FAIL}Impossibile trovare o utilizzare il link .m3u8 finale.{Bcolors.ENDC}")
            
    print("\n--- Fine del programma ---")
    # input(f"{Bcolors.OKBLUE}Premi Invio nel terminale per chiudere il browser...{Bcolors.ENDC}")
if __name__ == "__main__":
    main()
