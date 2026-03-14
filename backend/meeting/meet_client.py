import asyncio
from playwright.async_api import async_playwright

async def join_meeting(meet_link):
    try:
        async with async_playwright() as p:
            print("Launching Chrome...")
            context = await p.chromium.launch_persistent_context(
                user_data_dir="chrome_bot_profile",
                executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--start-maximized"
                ]
            )

            page = await context.new_page()

            page.on("close", lambda: print("PAGE CLOSED"))
            context.on("close", lambda: print("CONTEXT CLOSED"))

            print("Opening Google Meet...")
            await page.goto(meet_link)
            await page.wait_for_timeout(5000)

            # -----------------------------
            # 1️⃣ Click "Got it" popup
            # -----------------------------
            try:
                got_it = page.locator('button:has-text("Got it")')
                if await got_it.is_visible(timeout=3000):
                    print("Clicking 'Got it' popup")
                    await got_it.click()
            except:
                print("No 'Got it' popup")

            await page.wait_for_timeout(5000)

            # -----------------------------
            # 2️⃣ Disable microphone
            # -----------------------------
            print("Disabling microphone")
            try:
                await page.keyboard.press("Control+d")
            except:
                print("Mic toggle failed")

            await page.wait_for_timeout(2000)

            # -----------------------------
            # 3️⃣ Enter name
            # -----------------------------
            try:
                print("Entering name: bot")
                name_input = page.locator('input[placeholder="Your name"]')
                await name_input.fill("bot")
            except Exception as e:
                print("Name input failed:", e)

            await page.wait_for_timeout(1000)

            # -----------------------------
            # 4️⃣ Join meeting
            # -----------------------------
            print("Joining meeting...")
            try:
                await page.locator('button:has-text("Join now")').click(timeout=5000)
                print("Joined meeting")
            except:
                try:
                    await page.locator('button:has-text("Ask to join")').click(timeout=5000)
                    print("Requested to join meeting")
                except:
                    print("Join button not found")
            
            # -----------------------------
            # 5️⃣ Disable microphone again
            # -----------------------------
            print("Disabling microphone 2")
            try:
                await page.keyboard.press("Control+d")
            except:
                print("Mic toggle failed")

            await page.wait_for_timeout(2000)

            print("Meeting bot running...", flush=True)
            import time
            alone_since = None
            while True:
                try:
                    participant_count = 1
                    methods_found = []

                    # Method 1: Check "Show everyone" button by various attributes
                    try:
                        # Try several common attributes for the people/everyone button
                        locators = [
                            page.locator('button[aria-label*="Show everyone"]'),
                            page.locator('button[data-tooltip*="Show everyone"]'),
                            page.locator('button:has-text("Show everyone")'),
                            page.locator('button:has(i:has-text("people"))') # Icon-based fallback
                        ]
                        
                        for loc in locators:
                            if await loc.is_visible(timeout=500):
                                label = await loc.get_attribute("aria-label") or await loc.get_attribute("data-tooltip")
                                if label:
                                    import re
                                    match = re.search(r'\((\d+)\)', label)
                                    if match:
                                        count = int(match.group(1))
                                        participant_count = max(participant_count, count)
                                        methods_found.append(f"everyone_attr({count})")
                                        break
                    except Exception as e:
                        pass

                    # Method 2: Check for the counter element itself
                    try:
                        # Sometimes it's a div with a specific class or just text next to an icon
                        count_elements = await page.locator('.uGOf1d').all_text_contents()
                        for text in count_elements:
                            if text.isdigit():
                                count = int(text)
                                participant_count = max(participant_count, count)
                                methods_found.append(f"class_uGOf1d({count})")
                                break
                    except Exception as e:
                        pass

                    # Method 3: Count participant tiles/avatars
                    try:
                        # Google Meet often uses these classes for participant tiles
                        tile_selectors = [
                            'div[data-participant-id]',
                            '.Jt9Ci', # Common class for participant list items
                            '.Gv19re', # Common class for participant tiles
                            'div[role="listitem"]' # Generic list items in the side panel
                        ]
                        for sel in tile_selectors:
                            count = await page.locator(sel).count()
                            if count > 0:
                                participant_count = max(participant_count, count)
                                methods_found.append(f"tiles({sel}:{count})")
                    except Exception as e:
                        pass

                    is_alone = (participant_count <= 1)
                    
                    # Method 4: Fallback check for "Waiting for others to join" screen
                    if is_alone:
                        waiting_text = await page.locator('text="Waiting for others"').is_visible(timeout=500)
                        if waiting_text:
                            is_alone = True
                            methods_found.append("waiting_text_detected")
                    
                    if not methods_found:
                        print("[BOT DEBUG] WARNING: No participant detection succeeded. Defaulting to 'not alone' for safety.", flush=True)
                        is_alone = False
                    else:
                        debug_info = ", ".join(methods_found)
                        print(f"[BOT DEBUG] Participants detected: {participant_count} (Methods: {debug_info})", flush=True)
                        
                    if is_alone:
                        if alone_since is None:
                            alone_since = time.time()
                        
                        elapsed = int(time.time() - alone_since)
                        print(f"[BOT DEBUG] Bot IS ALONE. Total alone time: {elapsed}s", flush=True)
                        
                        if elapsed >= 10:
                            print("Bot has been alone for 10 seconds. Leaving meeting.", flush=True)
                            break
                    else:
                        alone_since = None
                        
                except Exception as e:
                    print(f"[BOT DEBUG] Error checking participants: {e}", flush=True)
                
                await asyncio.sleep(5)

    except asyncio.CancelledError:
        print("Meeting bot task was cancelled.")
    except Exception as e:
        print("BOT CRASH:", e)
