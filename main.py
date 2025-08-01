# Questo programma chiede all'utente il nome di un film o una serie,
# costruisce un URL di ricerca per onlineserietv.com,
# lo apre in un browser virtuale (headless) utilizzando SeleniumBase con la UC Mode abilitata,
# estrae i titoli dei risultati con Beautiful Soup 4 e li mostra nel terminale.

# Importiamo la classe SB (SeleniumBase Manager) per gestire il browser.
from seleniumbase import SB
import urllib.parse # Importiamo per codificare l'URL correttamente
from bs4 import BeautifulSoup # Importiamo Beautiful Soup per il parsing HTML

# Questo blocco di codice è per l'esecuzione diretta dello script.
# Inizializza SeleniumBase e avvia il processo di ricerca.
if __name__ == "__main__":
    print("Benvenuto! Inserisci il nome di un film o una serie TV:")

    # La funzione input() attende che l'utente digiti qualcosa
    # e prema Invio. Il testo digitato viene poi salvato nella variabile 'titolo'.
    titolo = input()

    # Stampiamo a schermo il titolo che l'utente ha inserito.
    print(f"Hai inserito: {titolo}")

    # Codifichiamo il titolo per l'URL. Questo è fondamentale per gestire
    # spazi e caratteri speciali nell'URL in modo corretto.
    titolo_codificato = urllib.parse.parse.quote_plus(titolo)

    # Costruiamo l'URL di ricerca.
    # L'URL base per la ricerca su onlineserietv.com è https://onlineserietv.com/?s=
    base_url = "https://onlineserietv.com/?s="
    search_url = f"{base_url}{titolo_codificato}"

    # Stampiamo l'URL di ricerca generato.
    print(f"L'URL di ricerca generato è: {search_url}")
    print("Avvio della ricerca in modalità headless...")

    # Utilizziamo il gestore SB() per avviare e chiudere il browser automaticamente.
    # Il parametro 'uc=True' abilita la UC Mode (Undetected ChromeDriver) per aggirare Cloudflare.
    # Il parametro 'headless=True' fa sì che il browser non sia visibile.
    with SB(uc=True, headless=True) as sb:
        # Apriamo l'URL generato nel browser virtuale.
        # sb.open() naviga all'URL specificato.
        sb.open(search_url)

        print("Attendo il caricamento dei risultati o la risoluzione di Cloudflare...")
        try:
            # Attendiamo che la griglia dei risultati sia visibile, utilizzando il selettore corretto.
            # Questo è un indicatore che la pagina si è caricata correttamente e Cloudflare è stato (si spera) superato.
            # Aumentiamo il timeout a 30 secondi per dare più tempo alla risoluzione del CAPTCHA.
            sb.wait_for_element("div#box_movies", timeout=30)
            print("Pagina dei risultati caricata con successo.")
        except Exception:
            print("Impossibile caricare la pagina dei risultati entro il tempo limite.")
            print("Potrebbe essere che Cloudflare stia ancora bloccando l'accesso o che i selettori HTML siano cambiati.")
            # Otteniamo comunque la sorgente della pagina per un'analisi diagnostica
            page_source_on_fail = sb.get_page_source()
            if "cloudflare" in page_source_on_fail.lower() or "just a moment" in page_source_on_fail.lower():
                print("Diagnosi: Sembra che Cloudflare CAPTCHA sia ancora attivo.")
            print("Il programma terminerà in quanto non è stato possibile ottenere i risultati.")
            # Usciamo dal programma se non riusciamo a superare Cloudflare o caricare i risultati.
            exit()

        # Otteniamo il codice sorgente HTML della pagina corrente.
        page_source = sb.get_page_source()

        # Creiamo un oggetto BeautifulSoup per analizzare l'HTML.
        soup = BeautifulSoup(page_source, 'html.parser')

        # Troviamo tutti i tag h2 con la classe 'imagen' all'interno del div 'box_movies'
        # Questo è un approccio più diretto e preciso per trovare i titoli.
        title_tags = soup.find('div', id='box_movies').find_all('h2', class_='imagen')

        print("\n--- Risultati della ricerca ---")
        if title_tags:
            found_count = 0
            for i, title_tag in enumerate(title_tags):
                # Otteniamo il testo del titolo e lo puliamo
                title_text = title_tag.text.strip()
                # Verifichiamo se l'input dell'utente è presente nel titolo estratto (case-insensitive)
                if titolo.lower() in title_text.lower():
                    print(f"{i+1}. {title_text}")
                    found_count += 1
            if found_count == 0:
                print(f"Nessun risultato trovato che contenga la parola '{titolo}'.")
        else:
            print("Nessun risultato trovato con i selettori attuali.")
            print("Verifica se i selettori HTML ('div#box_movies', 'h2.imagen') sono ancora validi.")

        print("--- Fine dei risultati ---")
        # Il browser verrà chiuso automaticamente quando si esce dal blocco 'with'.
