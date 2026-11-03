/* Native details retain controls and loaded DOM; toggles never send radio requests. */
(() => {
    const main=['bot-disclosure','repeater-management-disclosure','repeater-statistics-disclosure','repeater-comparison-disclosure'];
    document.addEventListener('toggle',event=>{
        const section=event.target;
        if(!(section instanceof HTMLDetailsElement)||!section.open)return;
        const peers=main.includes(section.id)?main.map(id=>document.getElementById(id)):
            section.classList.contains('statistics-accordion')?[...document.querySelectorAll('.statistics-accordion')]:[];
        for(const other of peers)if(other&&other!==section)other.open=false;
        if(section.classList.contains('statistics-accordion'))requestAnimationFrame(()=>window.MeshcoreStationStatisticsVisuals?.resize());
    },true);
})();
