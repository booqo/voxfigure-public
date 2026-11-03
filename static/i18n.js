window.vfI18n = (function () {
    function initialLang() {
        try {
            const saved = localStorage.getItem('mc_lang');
            if (saved === 'zh' || saved === 'en') return saved;
        } catch (e) { /* storage unavailable in sandboxed frames */ }
        const tag = ((document.documentElement && document.documentElement.lang) || '').toLowerCase();
        return tag.indexOf('zh') === 0 ? 'zh' : 'en';
    }
    let lang = initialLang();
    const dicts = {en:{navHome:'Workspace'},zh:{navHome:'工作台'}};
    const listeners = [];
    function register(en, zh) {
        Object.assign(dicts.en, en || {});
        Object.assign(dicts.zh, zh || {});
    }
    function t(key, params) {
        let text = (dicts[lang] && dicts[lang][key]) || dicts.en[key] || key;
        if (params) {
            text = text.replace(/\{(\w+)\}/g, function (match, name) {
                return Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match;
            });
        }
        return text;
    }
    function apply(root) {
        root = root || document;
        root.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.getAttribute('data-i18n')); });
        root.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = t(el.getAttribute('data-i18n-title')); });
        root.querySelectorAll('[data-i18n-ph]').forEach(el => { el.placeholder = t(el.getAttribute('data-i18n-ph')); });
        root.querySelectorAll('[data-i18n-aria]').forEach(el => { el.setAttribute('aria-label', t(el.getAttribute('data-i18n-aria'))); });
        root.querySelectorAll('[data-i18n-reason]').forEach(el => { el.setAttribute('data-reason', t(el.getAttribute('data-i18n-reason'))); });
        root.querySelectorAll('[data-i18n-g]').forEach(el => { el.setAttribute('data-g', t(el.getAttribute('data-i18n-g'))); });
        root.querySelectorAll('[data-lang]').forEach(el => {
            el.style.display = el.getAttribute('data-lang') === lang ? '' : 'none';
        });
        root.querySelectorAll('[data-en]').forEach(el => {
            el.textContent = el.getAttribute('data-' + lang) || el.getAttribute('data-en');
        });
        root.querySelectorAll('[data-en-ph]').forEach(el => {
            el.placeholder = el.getAttribute('data-' + lang + '-ph') || el.getAttribute('data-en-ph');
        });
        document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
        const label = lang === 'en' ? '中文' : 'EN';
        const b = document.getElementById('vfLangBtn');
        if (b) b.textContent = label;
        root.querySelectorAll('[data-lang-toggle]').forEach(el => { el.textContent = label; });
        listeners.forEach(f => { try { f(lang); } catch (e) {} });
    }
    function toggle() {
        lang = lang === 'en' ? 'zh' : 'en';
        try { localStorage.setItem('mc_lang', lang); } catch (e) {}
        apply();
    }
    function onChange(f) { listeners.push(f); }   // Notify page components after the language changes.
    return {get lang() { return lang; }, t, register, apply, toggle, onChange};
})();
