/* The same fake Companion fixture used by v5_milestone.cjs. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const url = 'http://127.0.0.1:8050';
const layouts = {desktop: [1280, 960, 'light'], mobile: [390, 844, 'dark']};

(async () => {
    for (const layout of process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(layouts)) {
        const [width, height, colorScheme] = layouts[layout];
        const browser = await chromium.launch({headless: true});
        try {
            const context = await browser.newContext({viewport: {width,height}, colorScheme, hasTouch: width < 800, isMobile: width < 800});
            const page = await context.newPage();
            const errors = [];
            page.on('pageerror', error => errors.push(error.message));
            await page.route('**/*', route => new URL(route.request().url()).origin === url ? route.continue() : route.abort());
            await page.goto(url);
            const waitText = (selector, text) => page.locator(selector).filter({hasText:text}).waitFor();
            await waitText('#open-station-settings', 'Settings');
            await page.locator('#open-station-settings').click();
            assert.equal(await page.locator('#dashboard-language').inputValue(), 'en');
            await page.locator('#dashboard-language').selectOption('de');
            await waitText('#open-station-settings', 'Einstellungen');
            assert.equal(await page.locator('html').getAttribute('lang'), 'de');
            assert.equal((await context.cookies()).find(c => c.name === 'meshcorestation-language')?.value, 'de');
            await page.reload();
            await waitText('#bot-status', 'Verbunden');
            await page.locator('#open-station-settings').click();
            assert.equal(await page.locator('#dashboard-language').inputValue(), 'de');
            await waitText('#display-settings h3', 'Anzeige von Datum und Uhrzeit');
            await page.locator('#close-station-settings').click();

            await page.locator('#open-repeaters').click();
            await waitText('#unlocated-repeaters > summary', 'Repeater ohne Koordinaten');
            await page.locator('#unlocated-repeaters > summary').click();
            const repeaterName = 'Registry ' + layout;
            const unlocated = page.locator('#unlocated-repeaters-list li').filter({hasText:repeaterName});
            const block = unlocated.getByRole('button', {name:'Repeater blockieren'});
            const key = (layout === 'desktop' ? '71' : '72').repeat(32);
            page.once('dialog', async dialog => { assert(dialog.message().includes(key)); await dialog.dismiss(); });
            await block.click();
            await block.waitFor();
            page.once('dialog', dialog => dialog.accept());
            await block.click();
            await waitText('#repeater-registry-status', 'Repeater lokal blockiert.');
            await unlocated.waitFor({state:'detached'});
            await page.locator('#blocked-repeaters > summary').click();
            const blocked = page.locator('#blocked-repeaters-list li').filter({hasText:repeaterName});
            await blocked.getByText(key, {exact:true}).waitFor();
            page.once('dialog', dialog => dialog.accept());
            await blocked.getByRole('button', {name:'Blockierung aufheben'}).click();
            await waitText('#repeater-registry-status', 'Blockierung aufgehoben.');
            await waitText('#blocked-repeaters-list', 'Es sind keine Repeater blockiert.');
            await page.locator('#close-repeaters').click();

            await page.locator('#open-companion').click();
            await waitText('#companion-title', 'Einstellungen');
            await waitText('label[for="bot-serial-port"]', 'Serielle Schnittstelle');
            await page.locator('#close-companion').click();
            await page.locator('#open-contacts').click();
            await waitText('#contacts-title', 'Companion-Kontakte');
            await page.locator('.contact-manage').first().click();
            await waitText('#repeater-login-title', 'Mit Repeater verbinden');
            await page.locator('#repeater-login-form button[type="submit"]').click();
            await waitText('#repeater-title', 'Repeater-Verwaltung');
            await page.locator('#repeater-tab-console').click();
            assert(await page.locator('#repeater-console-command').isDisabled());
            await page.locator('#repeater-close').click();
            await page.locator('#contacts-close').click();
            await page.locator('#open-channels').click();
            await waitText('#channels-title', 'Companion-Kanäle');
            await page.locator('#channels-list').getByText('Bot', {exact:true}).waitFor();
            await page.locator('#channels-close').click();

            await page.locator('#bot-disclosure > summary').click();
            await page.locator('#command-history-disclosure > summary').click();
            await waitText('#row-count', '200 von 205 Befehlen');
            await page.locator('#command-rows').getByText('Fixture Sender').first().waitFor();
            await page.locator('#command-rows button[data-details]').last().click();
            await waitText('#detail-title', 'Befehl Nr.');
            await waitText('#reply-tracking h3', 'Ausgehende Antworten');
            await page.locator('#close-details').click();

            await page.locator('#repeater-statistics-disclosure > summary').click();
            await waitText('#statistics-view-status', 'Gespeicherte Beobachtungen geladen');
            await page.locator('#statistics-map-section > summary').click();
            await waitText('.statistics-map-legend', 'beobachtete Nachbarn');
            await page.locator('#statistics-neighbor-map .leaflet-marker-icon').first().waitFor();
            await page.locator('#statistics-messages-section > summary').click();
            await page.getByRole('img', {name:'Beobachtete Textnachrichten pro Stunde'}).waitFor();
            await page.route('**/api/repeater-statistics/view?**', route => route.fulfill({
                status:504,json:{ok:false,error_code:'QUERY_TIMEOUT',error:'The server query budget was reached during classify. Refresh this period to resume classification. Recording continues; saved data is preserved.'}
            }));
            await page.locator('#statistics-refresh').click();
            await waitText('#statistics-view-error', 'Klassifizierung');
            await page.unroute('**/api/repeater-statistics/view?**');
            await page.locator('#repeater-comparison-disclosure > summary').click();
            await waitText('#comparison-status','Änderungen geladen');
            await page.locator('#comparison-description').fill('Fixture comparison');
            await page.locator('#comparison-save').click();
            await waitText('#comparison-status','Änderung gespeichert');
            let allowContinuation;
            const continueRequest = new Promise(resolve => { allowContinuation = resolve; });
            let comparisonCalls = 0;
            await page.route('**/api/repeater-comparison/view?**', async route => {
                if (++comparisonCalls === 1) {
                    await route.fulfill({status:504,json:{ok:false,error_code:'QUERY_TIMEOUT',stage:'classify',resume:true}});
                } else {
                    await continueRequest;
                    await route.continue();
                }
            });
            await page.locator('#comparison-period').selectOption('7');
            await waitText('#comparison-status','Gespeicherter Vergleich wird fortgesetzt');
            assert(await page.locator('#comparison-run').isDisabled());
            allowContinuation();
            await waitText('#comparison-status','Gespeicherter Vergleich geladen');
            await waitText('#comparison-results h3','Fixture comparison');
            assert.equal(comparisonCalls,2);
            await page.unroute('**/api/repeater-comparison/view?**');
            await page.route('**/api/repeater-comparison/view?**', route => route.fulfill({
                status:504,json:{ok:false,error_code:'QUERY_TIMEOUT',stage:'worker execution',resume:false}
            }));
            await page.locator('#comparison-run').click();
            await waitText('#comparison-error','Der Vergleichsdienst hat sein Zeitlimit überschritten');
            await waitText('#comparison-results.statistics-stale h3','Fixture comparison');
            assert(await page.locator('#comparison-run').isEnabled());
            await page.unroute('**/api/repeater-comparison/view?**');
            page.once('dialog', dialog => dialog.accept());
            await page.locator('#comparison-journal').getByRole('button', {name:'Löschen'}).click();
            await waitText('#comparison-journal','Keine Änderungen für diesen Repeater');
            await page.locator('#room-server-disclosure > summary').click();
            const room = page.frameLocator('#room-server-frame');
            await room.getByRole('heading',{name:'Ihre Räume'}).waitFor();
            await room.getByRole('button',{name:'Deaktivierten Raum erstellen'}).waitFor();
            assert.equal(await room.locator('html').getAttribute('lang'),'de');
            assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

            // A separate browser context can use English at the same time.
            const other = await browser.newContext();
            const english = await other.request.get(url+'/_dash-layout');
            assert.match(await english.text(), /Repeater Statistics/);
            assert(!(await other.cookies()).some(c => c.name === 'meshcorestation-language'));
            await page.locator('#open-station-settings').click();
            await page.locator('#dashboard-language').selectOption('en');
            await waitText('#open-station-settings', 'Settings');
            assert.equal(await page.locator('html').getAttribute('lang'), 'en');
            assert.deepEqual(errors,[]);
            console.log(`V6 German and English isolation, reload, live content, and ${layout} ${colorScheme} passed.`);
        } finally { await browser.close(); }
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
