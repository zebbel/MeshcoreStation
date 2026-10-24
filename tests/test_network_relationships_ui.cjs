const {JSDOM}=require('jsdom'),fs=require('node:fs'),assert=require('node:assert/strict');
const dom=new JSDOM('',{runScripts:'outside-only'}),w=dom.window;
w.eval(fs.readFileSync('meshcorestation/web/assets/ac_network_relationships.js','utf8'));
const {describe,explanation}=w.MeshcoreStationNetworkRelationships;
const observations={bidirectional:{weHear:3,theyHear:4,twoWay:true},unidirectional:{weHear:3,theyHear:0,twoWay:false},unknown:{weHear:null,theyHear:null}};
for(const [direction,fields] of Object.entries(observations)){
 for(const confidence of ['high','medium','low',null,'unexpected']){
  const r=describe({...fields,confidence});assert.equal(r.direction,direction);
  assert.equal(r.color,{bidirectional:'var(--green)',unidirectional:'var(--red)',unknown:'var(--muted)'}[direction]);
  assert.equal(r.dashArray,confidence==='low'?'8 7':['high','medium'].includes(confidence)?null:'2 6');
  assert.equal(r.confidence,['high','medium','low'].includes(confidence)?confidence:'unknown');
 }
}
assert.match(describe({weHear:0,theyHear:3}).observation,/Selected repeater → connected repeater/);
assert.match(describe({weHear:3,theyHear:0}).observation,/Connected repeater → selected repeater/);
assert.equal(describe({twoWay:true}).direction,'bidirectional','explicit analyzer twoWay confirms both directions');
assert.equal(describe({weHear:2,theyHear:3}).direction,'bidirectional','both positive counts confirm observations');
for(const record of [{weHear:0,theyHear:2,twoWay:true},{weHear:0,theyHear:0},{weHear:1},{theyHear:1},{twoWay:false},{weHear:'1',theyHear:0},{weHear:-1,theyHear:3}])assert.equal(describe(record).direction,'unknown');
assert.equal(describe({confidence:' MEDIUM '}).dashArray,null);
assert.equal(explanation,'Relationships are inferred from analyzer observations and do not necessarily represent verified direct radio links.');
dom.window.close();console.log('Relationship color/confidence matrix, incomplete/conflicting observations, direction semantics and English explanation passed.');
