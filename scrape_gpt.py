import sys, termios, tty, subprocess
import shutil, signal, time, random
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup, NavigableString
from pyvirtualdisplay import Display
import pyperclip, os

WebDriver=None
WebDriverDisplay=None
REAL_DISPLAY = os.environ.get("DISPLAY", ":0")
VncServer=None
VncWebSock=None
RunHidden=True
ServerLogFile=None
Count=0


def get_char():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

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
    global WebDriver
    last_height = WebDriver.execute_script("return document.body.scrollHeight")
    
    while True:
        current_position = WebDriver.execute_script("return window.pageYOffset")
        viewport_height = WebDriver.execute_script("return window.innerHeight")
        remaining = last_height - (current_position + viewport_height)

        # Fast reader: larger, quicker scrolls
        if remaining < 600:
            scroll_step = random.randint(80, 200)
        else:
            scroll_step = random.randint(300, 700)

        WebDriver.execute_script(f"window.scrollBy(0, {scroll_step});")

        # Short pauses (fast reading)
        time.sleep(random.uniform(pause_min, pause_max))

        # Rare small upward correction (quick skim behavior)
        if random.random() < 0.07:
            up_step = random.randint(50, 120)
            WebDriver.execute_script(f"window.scrollBy(0, -{up_step});")
            time.sleep(random.uniform(0.1, 0.3))

        # Handle dynamic/infinite scroll
        new_height = WebDriver.execute_script("return document.body.scrollHeight")
        if new_height > last_height:
            last_height = new_height

        # Stop when basically at bottom
        if remaining <= 5:
            break

    # Quick final push to ensure bottom
    WebDriver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

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

def html_to_text(element, indent=0):
    """Convert HTML to console-friendly text with proper code block isolation and indentation."""

    def extract_code(pre_block):
        """
        Extract code from <pre><code>, ignoring toolbar UI, preserving original line breaks.
        """
        code_tag = pre_block.find("code") or pre_block

        lines = []
        current_line = []

        for node in code_tag.descendants:
            # Ignore toolbar/UI elements
            if getattr(node, "name", None) in ["span", "button"]:
                if "class" in node.attrs and any(cl in node["class"] for cl in ["run-button", "language-label"]):
                    continue

            if isinstance(node, NavigableString):
                # Split text by newlines
                parts = str(node).splitlines()
                if parts:
                    for i, part in enumerate(parts):
                        if i == 0:
                            current_line.append(part)
                        else:
                            # Newline detected
                            lines.append("".join(current_line))
                            current_line = [part]
            elif getattr(node, "name", None) == "br":
                # Explicit <br> → new line
                lines.append("".join(current_line))
                current_line = []

        if current_line:
            lines.append("".join(current_line))

        # Remove trailing whitespace but preserve empty lines
        return "\n".join(line.rstrip() for line in lines)

    def detect_language(pre_block):
        """Detect language from class attributes in <pre> or <code>."""
        class_attr = ""
        if "class" in pre_block.attrs:
            class_attr = " ".join(pre_block.attrs["class"])
        code_tag = pre_block.find("code")
        if code_tag and "class" in code_tag.attrs:
            class_attr += " " + " ".join(code_tag.attrs["class"])
        for part in class_attr.split():
            if part.startswith("language-"):
                return part.split("language-")[1].capitalize()
        return None

    def process_node(node, indent_level=0):
        if isinstance(node, NavigableString):
            return str(node)

        # Headers
        if node.name in ["h1","h2","h3","h4","h5","h6"]:
            return "\n" + node.get_text(" ", strip=True).upper() + "\n"

        # Paragraphs
        if node.name == "p":
            return "\n" + process_children(node, indent_level).strip() + "\n"

        # Bold / strong
        if node.name == "strong":
            return node.get_text(" ", strip=True).upper()

        # Inline code
        if node.name == "code" and node.parent.name != "pre":
            return f"`{node.get_text(strip=False)}`"

        # Block code
        if node.name == "pre":
            code_text = extract_code(node)
            code_lines = [line.rstrip() for line in code_text.splitlines()]
            code_text = "\n".join(code_lines).strip()
            if not code_text:
                return ""
            width = max(len(line) for line in code_lines) if code_lines else 40
            border = "-" * min(width, 120)
            lang = detect_language(node)
            # Indent all lines according to list nesting
            indented_lines = "\n".join("  "*indent_level + line for line in code_lines)
            framed = f"{border}\n{indented_lines}\n{border}"
            if lang:
                framed = f"{lang}\n{framed}"
            return f"\n{framed}\n"

        # Tables
        if node.name == "table":
            return process_table(node, indent_level)

        # Unordered list
        if node.name == "ul":
            bullet_lines = []
            for li in node.find_all("li", recursive=False):
                line = "  "*indent_level + "* " + process_children(li, indent_level + 1).strip()
                bullet_lines.append(line)
            return "\n".join(bullet_lines) + "\n"

        # Ordered list
        if node.name == "ol":
            bullet_lines = []
            for i, li in enumerate(node.find_all("li", recursive=False), start=1):
                line = "  "*indent_level + f"{i}. " + process_children(li, indent_level + 1).strip()
                bullet_lines.append(line)
            return "\n".join(bullet_lines) + "\n"

        # Default: process children
        return process_children(node, indent_level)

    def process_children(parent, indent_level=0):
        parts = []
        for child in parent.children:
            parts.append(process_node(child, indent_level))
        return "".join(parts)

    def process_table(table, indent_level=0):
        rows = []
        col_widths = []
        for tr in table.find_all("tr"):
            row = []
            for td in tr.find_all(["td","th"]):
                row.append(td.get_text(" ", strip=True))
            if row:
                rows.append(row)
                if len(col_widths) < len(row):
                    col_widths.extend([0]*(len(row)-len(col_widths)))
                for i, cell in enumerate(row):
                    col_widths[i] = max(col_widths[i], len(cell))
        table_lines = []
        for r, row in enumerate(rows):
            padded_cells = [row[i].ljust(col_widths[i]) for i in range(len(row))]
            line = " | ".join(padded_cells)
            table_lines.append("  "*indent_level + line)
            if r == 0 and table.find("th"):
                sep = " | ".join("-"*col_widths[i] for i in range(len(row)))
                table_lines.append("  "*indent_level + sep)
        return "\n".join(table_lines) + "\n"

    result = process_children(element, indent)
    lines = result.splitlines()
    cleaned = [line.rstrip() for line in lines]
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
    global WebDriver
    WebDriver.execute_script("""
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
    global WebDriver, WebDriverDisplay, VncServer, VncWebSock, RunHidden, ServerLogFile
    RunHidden = hidden

    # Start virtual display
    if RunHidden:
        WebDriverDisplay = Display(visible=0, size=(1920, 1080))
        WebDriverDisplay.start()

        ServerLogFile = open("chat_servers.log", "a")  # 'a' = append mode

        # Give it time to start
        time.sleep(1)

        VNC_PORT=5900

        # Determine websockify path from current venv
        WebsockifyPath = os.path.join(sys.prefix, "bin", "websockify")

        # --- Start VNC server ---
        VncServer = subprocess.Popen([
            "x11vnc",
            "-display", f":{WebDriverDisplay.display}",
            "-rfbport", str(VNC_PORT),  # force fixed port
            "-forever",       # keep serving after client disconnects
            "-nopw",          # no password
            "-listen", "127.0.0.1",  # restrict to localhost
            "-xkb"            # better keyboard handling
        ],
            stdout=ServerLogFile,
            stderr=ServerLogFile
        )

        # Give it time to start
        time.sleep(1)

        # --- Launch websockify / noVNC ---
        # Add --web pointing to your noVNC folder
        NoVNCPath = "/home/frank/noVNC"  # adjust if your noVNC clone is elsewhere

        VncWebSock = subprocess.Popen([
            WebsockifyPath,
            "6080",                  # port for browser
            f"127.0.0.1:{VNC_PORT}", # the VNC server to proxy
            "--web", NoVNCPath       # serve noVNC HTML/JS files
        ],
            stdout=ServerLogFile,
            stderr=ServerLogFile
        )
        # Give it time to start
        time.sleep(1)


    options = uc.ChromeOptions()
    options.binary_location = "/snap/bin/chromium"  # adjust path
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    WebDriver = uc.Chrome(version_main=146, options=options)
    WebDriver.get(url)
    monitor_stayloggedout()
    print(WebDriver.title)

def EndSession():
    global WebDriverDisplay, WebDriver, VncServer, VncWebSock

    def kill_chrome():
        try:
            subprocess.run(["pkill", "-f", "chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-f", "chromedriver"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    if WebDriver:
        try:
            WebDriver.quit()
        except Exception:
            pass
        WebDriver = None

    # Give Chrome time to die gracefully
    kill_chrome()
    time.sleep(2)

    if VncWebSock:
        try:
            VncWebSock.terminate()
        except Exception:
            pass
        VncWebSock = None
    time.sleep(2)

    if VncServer:
        try:
            VncServer.terminate()
        except Exception:
            pass
        VncServer = None

    time.sleep(2)

    if WebDriverDisplay:
        try:
            WebDriverDisplay.stop()
        except Exception:
            pass
        WebDriverDisplay = None

def GetResponse(prompt):
    global Count
    stable_text=""

    try:
        #wait for the copy button count to increase
        #print(f"Count:{Count}")
        selector = "button.text-token-text-secondary"
        new_count = wait_for_visible_count_to_increase(WebDriver, selector, Count, timeout=30)
        Count = new_count
        #print(f"NewCount:{new_count}")
        #print(3)
        
        # Wait for the text changes to become stable
        locator = (By.CSS_SELECTOR, "main")
        new_stable_text = wait_for_text_stable(WebDriver, locator, stable_text, timeout=60, poll_frequency=0.2, stable_time=1.3)
        stable_text = new_stable_text
        #print(f"Stable Text:{stable_text}")
        #print(4)
        # Parse HTML
        soup = BeautifulSoup(WebDriver.page_source, "html.parser")
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

def PromptLoop():
    global WebDriver, WebDriverDisplay, ServerLogFile, REAL_DISPLAY
    promptText = ""
    help_text = """
    quit - ends the session closing the webdriver
    view display - displays the chromium window in vnc
    """

    def write_prompt(clearPromptfield=False):
        nonlocal promptText, prompt_field
        if(clearPromptfield):
            for _ in promptText:
                prompt_field.send_keys(Keys.BACKSPACE)
        promptText = ""
        print(f"\033[34m\nYou:\033[0m", end="", flush=True)

    def GetPromptField():
        nonlocal promptText
        prompt_field = WebDriverWait(WebDriver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//p[contains(@class, 'placeholder')]"))
        )
        prompt_field.click()
        write_prompt()        
        return prompt_field

    # simulate a copy paste of the "system prompt"
    pyperclip.copy("During this conversation keep all responses as terse as possible while relaying all of the requested information. ")
    prompt_field = GetPromptField()
    prompt_field.send_keys(Keys.CONTROL, "v")  #paste from the clipboard

    while True:
        key = get_char()

        if key == "\r" or key == "\n":  # Enter

            print() # add the newline to the console
            if promptText.lower() == "quit":
                print("Exiting ...")
                break  # stops the loop
            elif promptText.lower() == "view display":
                # --- Launch VCN Viewer in Firefox on REAL display ---
                ffenv = os.environ.copy() #copy the env variable for modification so you dont disrupt the processes using the virtual display
                ffenv["DISPLAY"] = REAL_DISPLAY   # force real screen
                subprocess.Popen(
                    [
                        "firefox", 
                        #"--new-instance",   # important
                        #"--no-remote",      # prevents reuse of hidden instance
                        "http://127.0.0.1:6080/vnc.html"  # Open the URL using the default browser chosen by the OS
                    ],
                    env=ffenv,
                    stdout=ServerLogFile,
                    stderr=ServerLogFile
                )
                write_prompt(True)

            elif promptText.lower() == "/help":
                print(help_text)
                write_prompt(True)
            else:
                submit_btn = WebDriverWait(WebDriver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'composer-submit-btn')]"))
                )
                submit_btn.click()
                ColouriseLastInput("You: " + promptText)
                print(GetResponse(promptText).replace("CHATGPT SAID:\n\n","\nBot:"))
                prompt_field = GetPromptField()

        elif key == "\x7f":  # Backspace
            promptText = promptText[:-1] 
            prompt_field.send_keys(Keys.BACKSPACE)
            print("\b \b", end="", flush=True) # move back on char write empty space over the char then move back one again

        else:
            promptText += key #build prompt string
            prompt_field.send_keys(key)
            print(key, end="", flush=True)



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

PromptLoop()

EndSession()

