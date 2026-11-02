(() => {
 document.addEventListener('click',e=>{
  const dialog=document.getElementById('station-settings-dialog');
  if(e.target.closest('#open-station-settings')&&!dialog.open)dialog.showModal();
  if(e.target.closest('#close-station-settings'))dialog.close();
 });
})();
