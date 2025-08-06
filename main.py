# Questo programma cerca film o serie TV, naviga verso la loro pagina,
# e cerca di estrarre il link .m3u8 del flusso video ispezionando le richieste di rete.
# Utilizza SeleniumBase in modalità UC per aggirare le protezioni di Cloudflare.

# Importiamo le librerie necessarie.
from seleniumbase import SB
import urllib.parse
from bs4 import BeautifulSoup
import re
import time
import argparse
import sys

# --- OPZIONI DI DEBUG ---
# Imposta su True per attivare la stampa dettagliata per il debug.
verbose_debug = True

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

# =========================================================================
# Logica principale del programma.
# =========================================================================
if __name__ == "__main__":
    # Configura il parser degli argomenti da riga di comando
    parser = argparse.ArgumentParser(description='Cerca e trova link .m3u8 per film e serie TV.')
    parser.add_argument('--link', type=str, help='Inserisci il link diretto alla pagina del film o serie TV.')
    args = parser.parse_args()

    # Nuove variabili per la configurazione del player
    SELECT_PLAYER_ID = "sel_player"  # Corrisponde all'attributo `name` dell'elemento <select>
    PLAYER_NAME_FLEXI = "flexy"      # Corrisponde all'attributo `value` del player Flexy

    selected_link = args.link

    # Inizializziamo SeleniumBase in modalità Undetected-Chromedriver per bypassare Cloudflare
    with SB(uc=True, headless=False) as sb:
        if not selected_link:
            print(f"{Bcolors.OKBLUE}Benvenuto! Inserisci il nome di un film o una serie TV:{Bcolors.ENDC}")
            titolo = input()

            print(f"Hai inserito: {Bcolors.WARNING}{titolo}{Bcolors.ENDC}")
            titolo_codificato = urllib.parse.quote_plus(titolo)
            base_url = "https://onlineserietv.com/?s="
            search_url = f"{base_url}{titolo_codificato}"

            print(f"L'URL di ricerca generato è: {Bcolors.OKCYAN}{search_url}{Bcolors.ENDC}")
            print("Avvio della ricerca...")

            sb.open(search_url)

            print("Attendo il caricamento dei risultati o la risoluzione di Cloudflare...")
            try:
                # Aspetta che l'elemento principale della pagina dei risultati sia visibile
                sb.wait_for_element("div#box_movies", timeout=30)
                print(f"{Bcolors.OKGREEN}Pagina dei risultati caricata con successo.{Bcolors.ENDC}")
            except Exception:
                print(f"{Bcolors.FAIL}Impossibile caricare la pagina dei risultati entro il tempo limite.{Bcolors.ENDC}")
                page_source_on_fail = sb.get_page_source()
                if "cloudflare" in page_source_on_fail.lower() or "just a moment" in page_source_on_fail.lower():
                    print("Diagnosi: Sembra che Cloudflare CAPTCHA sia ancora attivo.")
                print("Il programma terminerà in quanto non è stato possibile ottenere i risultati.")
                sys.exit()
            
            page_source = sb.get_page_source()
            if verbose_debug:
                print(f"\n{Bcolors.HEADER}--- DEBUG: Codice sorgente della pagina di ricerca ---{Bcolors.ENDC}")
                print(page_source)
                print(f"{Bcolors.HEADER}----------------------------------------------------{Bcolors.ENDC}")

            soup = BeautifulSoup(page_source, 'html.parser')
            movie_items = soup.find('div', id='box_movies').find_all('div', class_='movie')

            print("\n--- Risultati della ricerca ---")
            if movie_items:
                found_results = []
                max_len = 0
                for item in movie_items:
                    title_tag = item.find('h2')
                    link_tag = item.find('a')
                    if title_tag and link_tag:
                        title_text = title_tag.text.strip()
                        link_url = link_tag['href']
                        content_type = "Serie TV" if "/serietv/" in link_url else "Film"
                        
                        if titolo.lower() in title_text.lower():
                            found_results.append({
                                'title': title_text,
                                'link': link_url,
                                'type': content_type
                            })
                            if len(title_text) > max_len:
                                max_len = len(title_text)

                if found_results:
                    name_col_width = max(max_len, len("Name"))
                    type_col_width = max(len("Serie TV"), len("Type"))
                    table_width = name_col_width + len("Index") + type_col_width + 8
                    
                    print(f"{Bcolors.OKCYAN}{'-' * table_width}{Bcolors.ENDC}")
                    print(f"{Bcolors.OKCYAN}| {'Index':<5} | {'Name':<{name_col_width}} | {'Type':<{type_col_width}} |{Bcolors.ENDC}")
                    print(f"{Bcolors.OKCYAN}{'-' * table_width}{Bcolors.ENDC}")
                    
                    colors = [Bcolors.FAIL, Bcolors.OKGREEN, Bcolors.WARNING, Bcolors.OKBLUE, Bcolors.HEADER, Bcolors.OKCYAN]
                    for i, result in enumerate(found_results):
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
                            if 0 <= index < len(found_results):
                                selected_link = found_results[index]['link']
                                break
                            else:
                                print(f"{Bcolors.FAIL}Selezione non valida. Inserisci un numero tra 1 e {len(found_results)}.{Bcolors.ENDC}")
                        except ValueError:
                            print(f"{Bcolors.FAIL}Input non valido. Inserisci un numero.{Bcolors.ENDC}")
                else:
                    print(f"{Bcolors.FAIL}Nessun risultato trovato che contenga la parola '{titolo}'.{Bcolors.ENDC}")
                    sys.exit()
            else:
                print(f"{Bcolors.FAIL}Nessun risultato trovato con i selettori attuali.{Bcolors.ENDC}")
                sys.exit()
        
        # Logica per l'estrazione del link .m3u8, comune a entrambi i percorsi
        print(f"{Bcolors.OKGREEN}Apertura del link: {selected_link}{Bcolors.ENDC}")
        sb.open(selected_link)
        
        # Aggiungiamo un'attesa esplicita per assicurarci che la pagina sia completamente caricata
        sb.wait_for_ready_state_complete()
        
        print(f"{Bcolors.WARNING}\n--- Ricerca del link .m3u8 ---{Bcolors.ENDC}")
        
        # Passaggio 1: Seleziona il player "Flexy" usando le nuove variabili
        try:
            print(f"{Bcolors.OKCYAN}Tentativo di selezionare il player '{PLAYER_NAME_FLEXI}'...{Bcolors.ENDC}")
            # Cerca e clicca sul selettore del player
            sb.wait_for_element_clickable(f"select[name='{SELECT_PLAYER_ID}']", timeout=10)
            sb.click(f"select[name='{SELECT_PLAYER_ID}']")
            
            # Cerca e clicca sull'opzione 'Flexy'
            sb.wait_for_element_clickable(f"select[name='{SELECT_PLAYER_ID}'] option[value='{PLAYER_NAME_FLEXI}']", timeout=5)
            sb.click(f"select[name='{SELECT_PLAYER_ID}'] option[value='{PLAYER_NAME_FLEXI}']")
            
            # Aggiungiamo una breve attesa per permettere al player di caricarsi dopo la selezione
            time.sleep(2)
            
            print(f"{Bcolors.OKGREEN}Player '{PLAYER_NAME_FLEXI}' selezionato con successo.{Bcolors.ENDC}")
        except Exception as e:
            print(f"{Bcolors.FAIL}Errore nella selezione del player '{PLAYER_NAME_FLEXI}': {e}{Bcolors.ENDC}")
        
        # Passaggio 2: Clicca sul pulsante 'Play' con una logica più robusta
        print(f"{Bcolors.OKCYAN}Tentativo di cliccare sul pulsante di riproduzione...{Bcolors.ENDC}")
        button_clicked = False
        
        # Nuovo selettore per il pulsante Play all'interno di un player Plyr
        try:
            sb.wait_for_element_visible("div.plyr__controls button.plyr__control[data-plyr='play']", timeout=10)
            sb.click("div.plyr__controls button.plyr__control[data-plyr='play']")
            print(f"{Bcolors.OKGREEN}Pulsante di riproduzione (Plyr) trovato e cliccato.{Bcolors.ENDC}")
            button_clicked = True
        except Exception:
            print(f"{Bcolors.WARNING}Pulsante di riproduzione (Plyr) non trovato. Provo con i selettori precedenti.{Bcolors.ENDC}")

        # Se il nuovo selettore non funziona, prova i selettori precedenti come fallback
        if not button_clicked:
            # Tentativo 1: Cerca il pulsante specifico (img[alt='Player dello Streaming'])
            try:
                sb.wait_for_element_visible("a img[alt='Player dello Streaming']", timeout=5)
                sb.click("a img[alt='Player dello Streaming']")
                print(f"{Bcolors.OKGREEN}Pulsante di riproduzione specifico trovato e cliccato.{Bcolors.ENDC}")
                button_clicked = True
            except Exception:
                print(f"{Bcolors.WARNING}Pulsante di riproduzione specifico non trovato. Provo con il prossimo selettore.{Bcolors.ENDC}")

        if not button_clicked:
            # Tentativo 2: Cerca il pulsante standard (vjs-big-play-button)
            try:
                sb.wait_for_element_visible("div#vplayer button.vjs-big-play-button", timeout=5)
                sb.click("div#vplayer button.vjs-big-play-button")
                print(f"{Bcolors.OKGREEN}Pulsante di riproduzione standard (vjs) trovato e cliccato.{Bcolors.ENDC}")
                button_clicked = True
            except Exception:
                print(f"{Bcolors.FAIL}Pulsante di riproduzione standard non trovato.{Bcolors.ENDC}")

        if not button_clicked:
            print(f"{Bcolors.FAIL}Nessun pulsante di riproduzione valido trovato. Procedo comunque con la ricerca del link.{Bcolors.ENDC}")

        # Aggiungiamo un ritardo più lungo dopo aver cliccato play, per dare tempo al browser
        # di inviare la richiesta del flusso video.
        print(f"{Bcolors.OKCYAN}Attendo 10 secondi per consentire il caricamento del flusso video...{Bcolors.ENDC}")
        time.sleep(10)
        
        m3u8_link = None
        try:
            print(f"{Bcolors.OKCYAN}Attendo la richiesta per il link .m3u8...{Bcolors.ENDC}")
            # Il pattern regex aggiornato è ancora più specifico per gestire URL con o senza parametri.
            m3u8_link = sb.wait_for_request(r'https?://[^\s\'"]+\.m3u8.*', timeout=10)
            print(f"{Bcolors.OKGREEN}Link master.m3u8 trovato tramite richieste di rete: {m3u8_link}{Bcolors.ENDC}")
        except Exception:
            print(f"{Bcolors.FAIL}Nessun link master.m3u8 trovato dopo tutti i tentativi.{Bcolors.ENDC}")
        
        print("\n--- Fine dei risultati ---")
        input(f"{Bcolors.OKBLUE}Premi Invio nel terminale per chiudere il browser...{Bcolors.ENDC}")
