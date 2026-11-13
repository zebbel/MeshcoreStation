(() => {
    document.addEventListener('change', event => {
        if (event.target.id === 'dashboard-language') {
            window.MeshcoreStationI18n?.select(event.target.value);
        }
    });
})();
