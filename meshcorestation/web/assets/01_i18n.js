/* Dashboard strings are selected before any feature assets initialize. */
(() => {
    'use strict';
    const catalogs = window.MeshcoreStationCatalogs || {en: {}};
    const supported = code => Object.hasOwn(catalogs, code);
    const preferenceCookie = 'meshcorestation-language';
    const language = supported(document.documentElement.lang) ? document.documentElement.lang : 'en';
    document.documentElement.lang = language;

    function t(id, ...values) {
        if (typeof id !== 'string') return id;
        const catalog = catalogs[language];
        const message = (Object.hasOwn(catalog, id) && catalog[id]) ||
            (Object.hasOwn(catalogs.en, id) && catalogs.en[id]) || id;
        return message.replace(/\{(\d+)\}/g, (match, i) => i < values.length ? String(values[i]) : match);
    }

    function translatedError(message) {
        if (typeof message !== 'string') return message;
        const exact = t(message);
        if (exact !== message) return exact;
        for (const [pattern, id] of [
            [/^Received (\d+) completed aggregate records; sequence cursor (\d+)\/(\d+)\.$/, 'Received {0} completed aggregate records; sequence cursor {1}/{2}.'],
            [/^Received (\d+) legacy neighbor rows \(reported total (\d+)\)\.$/, 'Received {0} legacy neighbor rows (reported total {1}).'],
            [/^Expected (-?[\d.]+)–(-?[\d.]+) in steps of ([\d.]+)\.$/, 'Expected {0}–{1} in steps of {2}.'],
            [/^Expected (-?[\d.]+)–(-?[\d.]+)\.$/, 'Expected {0}–{1}.'],
            [/^Use at most (\d+) UTF-8 bytes without control characters\.$/, 'Use at most {0} UTF-8 bytes without control characters.'],
            [/^The server query budget was reached during ([\w -]+)\. Refresh this period to resume classification\. Recording continues; saved data is preserved\.$/, 'The server query budget was reached during {0}. Refresh this period to resume classification. Recording continues; saved data is preserved.'],
            [/^The server query budget was reached during ([\w -]+)\. Try refreshing the saved view or choosing a shorter period\. Recording continues; saved data is preserved\.$/, 'The server query budget was reached during {0}. Try refreshing the saved view or choosing a shorter period. Recording continues; saved data is preserved.']
        ]) {
            const match = pattern.exec(message);
            if (match) return t(id, ...match.slice(1).map(value => t(value)));
        }
        return message;
    }

    const attributes = ['aria-label', 'title', 'placeholder', 'alt'];
    function translateMarkup(root) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            if (node.nodeType === Node.TEXT_NODE) {
                if (node.parentElement?.closest('script, style, code, kbd, pre, textarea')) continue;
                const value = node.data.trim();
                if (value) node.data = node.data.replace(value, () => t(value));
            } else {
                for (const attribute of attributes) {
                    const value = node.getAttribute(attribute);
                    if (value) node.setAttribute(attribute, t(value));
                }
            }
        }
    }

    function html(markup) {
        if (language === 'en') return markup;
        const template = document.createElement('template');
        template.innerHTML = markup;
        translateMarkup(template.content);
        return template.innerHTML;
    }

    function select(code) {
        if (!supported(code) || code === language) return;
        const secure = location.protocol === 'https:' ? '; Secure' : '';
        document.cookie = `${preferenceCookie}=${encodeURIComponent(code)}; Path=/; Max-Age=31536000; SameSite=Lax${secure}`;
        location.reload();
    }

    window.MeshcoreStationI18n = {t, html, translatedError, translateMarkup, language, select};
})();
