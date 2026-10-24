/* Analyzer observations only. Direction and confidence are independent. */
(() => {
    const explanation='Relationships are inferred from analyzer observations and do not necessarily represent verified direct radio links.';
    const count=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0?v:null;
    function describe(n){
        const we=count(n.weHear),they=count(n.theyHear);
        let direction='unknown',observation='Direction unknown: observations are incomplete or inconsistent.';
        if((we>0&&they>0)||(n.twoWay===true&&we!==0&&they!==0)){
            direction='bidirectional';observation='Bidirectional: observations reported in both directions.';
        }else if(n.twoWay!==true&&((we>0&&they===0)||(they>0&&we===0))){
            direction='unidirectional';observation=we>0?'Connected repeater → selected repeater (weHear).':'Selected repeater → connected repeater (theyHear).';
        }
        const confidence=typeof n.confidence==='string'?n.confidence.trim().toLowerCase():'';
        const level=['high','medium','low'].includes(confidence)?confidence:'unknown';
        return {direction,observation,we,they,confidence:level,
            color:{bidirectional:'var(--green)',unidirectional:'var(--red)',unknown:'var(--muted)'}[direction],
            // Unknown confidence is explicitly dotted, never silently promoted.
            dashArray:level==='low'?'8 7':level==='unknown'?'2 6':null};
    }
    window.MeshcoreStationNetworkRelationships={describe,explanation};
})();
