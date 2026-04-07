import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup, NavigableString
from pyvirtualdisplay import Display
import shutil
import random
import signal
import time
import sys
Driver=None
HiddenDisplay=None
RunHidden=True
Count=0

def typeit(self, text):
    time.sleep(random.uniform(0.1, 0.3))
    for char in text:
        self.send_keys(char)
        
        if char == " ":
            time.sleep(random.uniform(0.08, 0.2))
        elif char in ",.!?":
            time.sleep(random.uniform(0.2, 0.4))  # pause at punctuation
        else:
            time.sleep(random.uniform(0.02, 0.07))

def scrollit( pause_min=0.2, pause_max=0.8):
    global Driver
    last_height = Driver.execute_script("return document.body.scrollHeight")
    
    while True:
        current_position = Driver.execute_script("return window.pageYOffset")
        viewport_height = Driver.execute_script("return window.innerHeight")
        remaining = last_height - (current_position + viewport_height)

        # Fast reader: larger, quicker scrolls
        if remaining < 600:
            scroll_step = random.randint(80, 200)
        else:
            scroll_step = random.randint(300, 700)

        Driver.execute_script(f"window.scrollBy(0, {scroll_step});")

        # Short pauses (fast reading)
        time.sleep(random.uniform(pause_min, pause_max))

        # Rare small upward correction (quick skim behavior)
        if random.random() < 0.07:
            up_step = random.randint(50, 120)
            Driver.execute_script(f"window.scrollBy(0, -{up_step});")
            time.sleep(random.uniform(0.1, 0.3))

        # Handle dynamic/infinite scroll
        new_height = Driver.execute_script("return document.body.scrollHeight")
        if new_height > last_height:
            last_height = new_height

        # Stop when basically at bottom
        if remaining <= 5:
            break

    # Quick final push to ensure bottom
    Driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

def wait_for_visible_count_to_increase(Driver, selector, previous_count, timeout=10):
    """
    Wait until the number of visible elements matching selector increases.
    Returns the new visible count.
    """
    def condition(drv):
        scrollit() #scroll to the bottom
        elements = drv.find_elements(By.CSS_SELECTOR, selector)
        # Filter only visible elements
        visible_elements = [el for el in elements if el.is_displayed()]
        current_count = len(visible_elements)
        if current_count > previous_count:
            return current_count  # Will be returned by WebDriverWait.until
        return False  # Keep waiting

    new_count = WebDriverWait(Driver, timeout).until(condition)
    return new_count

def html_to_text(element):
    text_lines = []

    def extract_code(container):
        """Reconstruct code from span/br or pre/code structures"""
        lines = []
        current_line = []

        for node in container.descendants:
            if isinstance(node, NavigableString):
                current_line.append(str(node))
            elif node.name == "br":
                lines.append("".join(current_line))
                current_line = []

        if current_line:
            lines.append("".join(current_line))

        return "\n".join(line.rstrip() for line in lines)

    def process_node(node):
        """Process a node intelligently"""
        if isinstance(node, NavigableString):
            return str(node)

        # HEADERS
        if node.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            return "\n" + node.get_text(" ", strip=True).upper() + "\n"

        # PARAGRAPHS
        if node.name == "p":
            return "\n" + process_children(node).strip() + "\n"

        # STRONG / BOLD
        if node.name == "strong":
            return node.get_text(" ", strip=True).upper()

        # INLINE CODE
        if node.name == "code" and node.parent.name != "pre":
            return f"`{node.get_text(strip=False)}`"

        # BLOCK CODE
        if node.name == "pre":
            code_text = extract_code(node)
            return f"\n\n{code_text}\n\n"

        # LISTS
        #if node.name == "ul":
        #    return "\n".join(f"* {li.get_text(strip=True)}" for li in node.find_all("li", recursive=False)) + "\n"

        #if node.name == "ol":
        #   return "\n".join(f"{i+1}. {li.get_text(strip=True)}"
        #                     for i, li in enumerate(node.find_all("li", recursive=False))) + "\n"

        if node.name == "ul":
            # Use asterisk for unordered lists
            bullet_lines = []
            for li in node.find_all("li", recursive=False):
                bullet_lines.append(f"* {li.get_text(strip=True)}")
            return "\n".join(bullet_lines) + "\n"

        if node.name == "ol":
            # Use numbers for ordered lists
            bullet_lines = []
            for i, li in enumerate(node.find_all("li", recursive=False), start=1):
                bullet_lines.append(f"{i}. {li.get_text(strip=True)}")
            return "\n".join(bullet_lines) + "\n"


        # DIV / SECTION — detect code-like blocks
        if node.name in ["div", "section"]:
            spans = node.find_all("span")
            brs = node.find_all("br")

            # Heuristic: code block (like ChatGPT / CodeMirror)
            if len(spans) >= 3 and len(brs) >= 1:
                code_text = extract_code(node)
                return f"\n\n{code_text}\n\n"

            return process_children(node)

        # DEFAULT
        return process_children(node)

    def process_children(parent):
        parts = []
        for child in parent.children:
            parts.append(process_node(child))
        return "".join(parts)

    result = process_children(element)

    # Cleanup: fix excessive whitespace but KEEP code formatting
    lines = result.splitlines()
    cleaned = []
    for line in lines:
        cleaned.append(line.rstrip())

    return "\n".join(cleaned).strip()

def wait_for_text_stable(Driver, locator, last_result_stable_text, timeout=60, poll_frequency=0.5, stable_time=1.0):
    """
    Wait until the text of an element stops changing.

    Args:
        Driver: Selenium WebDriver
        locator: tuple, e.g., (By.CSS_SELECTOR, "p[data-is-last-node]")
        timeout: max wait time in seconds
        poll_frequency: how often to check the element
        stable_time: how long text must remain unchanged before returning
    Returns:
        The stable text
    """
    end_time = time.time() + timeout
    last_text = ""
    stable_since = None

    while time.time() < end_time:
        try:
            element = Driver.find_element(*locator)
            element_html = element.get_attribute("outerHTML")
            # Parse with BeautifulSoup
            element_soup = BeautifulSoup(element_html, "html.parser")
            # Extract text
            current_text = element_soup.get_text(strip=True)

        except:
            current_text = ""

        if current_text==last_result_stable_text:
            last_text = current_text
            stable_since = None
        elif current_text == last_text and current_text != "":
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= stable_time:
                return current_text  # text has been stable long enough
        else:
            last_text = current_text
            stable_since = None

        scrollit() #scroll to the bottom
        time.sleep(poll_frequency)

    # Timeout reached, return last observed text
    return last_text

def monitor_stayloggedout():
    global Driver
    Driver.execute_script("""
        const observer = new MutationObserver(() => {
            const links = document.querySelectorAll('a[href="#"]');

            for (const link of links) {
                if (link.textContent.toLowerCase().includes("stay logged out")) {
                    link.click();
                    console.log("Clicked 'Stay logged out'");
                    break;
                }
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    """)

def InitWebSession(url, hidden=True):
    global Driver
    global HiddenDisplay
    global RunHidden 
    RunHidden = hidden

    # Start virtual display
    if RunHidden:
        HiddenDisplay = Display(visible=0, size=(1920, 1080))
        HiddenDisplay.start()

    options = uc.ChromeOptions()
    options.binary_location = "/snap/bin/chromium"  # adjust path
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    Driver = uc.Chrome(version_main=146, options=options)
    Driver.get(url)
    monitor_stayloggedout()

    print(Driver.title)
    time.sleep(random.uniform(1, 3))

def EndSession():
    # Cleanup
    Driver.quit()
    if(RunHidden):
        HiddenDisplay.stop()

def SendPrompt(prompt):
    global Count
    stable_text=""

    try:
        prompt_field = Driver.find_element(By.XPATH, "//p[contains(@class, 'placeholder')]")
        prompt_field.click()

        typeit( prompt_field, prompt )  
        #print(1)
        btn = Driver.find_element(By.XPATH, "//button[contains(@class, 'composer-submit-btn')]")
        btn.click()
        #print(2)

        #wait for the copy button count to increase
        #print(f"Count:{Count}")
        selector = "button.text-token-text-secondary"
        new_count = wait_for_visible_count_to_increase(Driver, selector, Count, timeout=30)
        Count = new_count
        #print(f"NewCount:{new_count}")
        #print(3)
        
        # Wait for the text changes to become stable
        locator = (By.CSS_SELECTOR, "main")
        new_stable_text = wait_for_text_stable(Driver, locator, stable_text, timeout=60, poll_frequency=0.2, stable_time=1.3)
        stable_text = new_stable_text
        #print(f"Stable Text:{stable_text}")
        #print(4)
        # Parse HTML
        soup = BeautifulSoup(Driver.page_source, "html.parser")
        #print(5)
        # Step 2: get all sections
        sections = soup.find_all("section")
        #print(6)
        # Step 3: get text of the last section
        lastsection = sections[-1]
        #print(f"Sections Count:{len(sections)}")
        #print(7) 
        #section_text = sec.get_text(strip=True).lower()
        return  html_to_text(lastsection)

    except Exception as e:
        print("Error:", e)

def get_line_count(text):
    width = shutil.get_terminal_size().columns
    lines = 0
    for line in text.split('\n'):
        lines += (len(line) // width) + 1
    return lines

def clear_lines(n):
    for _ in range(n):
        print("\033[F\033[K", end='')  # move up + clear line

def ColouriseLastInput(prompt):
    line_count = get_line_count(prompt)
    clear_lines(line_count)
    print(f"\033[34m{prompt.capitalize()}\033[0m")


### Script ###

# Register signal handler for SIGINT (Ctrl+C) and SIGTERM (termination signal)
signal.signal(signal.SIGINT, EndSession)  # For Ctrl+C (interrupt)
signal.signal(signal.SIGTERM, EndSession)  # For termination signal
signal.signal(signal.SIGHUP, EndSession)  # For Hangup

try:
    runHidden = sys.argv[1].lower() in ['true', '1', 't', 'y', 'yes'] #access the first arg
except:
    runHidden = True

InitWebSession("https://chatgpt.com", runHidden)

firstPrompt=True
while True:

    prompt = input(f"\033[34m\nYou:\033[0m")

    if prompt.lower() == "quit":
        print("Exiting loop...")
        EndSession()
        break  # stops the loop

    #print the prompt to the screen so its pretty
    ColouriseLastInput("You: " + prompt)

    # include a "system prompt" on the first request
    if firstPrompt:
        prompt = "During this conversation keep all responses as terse as possible while relaying all of the requested information. " + prompt
        firstPrompt=False

    #send the prompt
    response = SendPrompt(prompt)
    #print("\033[F\033[K", end="")  # F = up one line, K = clear line
    print(response.replace("CHATGPT SAID:\n\n","\nBot:"))
