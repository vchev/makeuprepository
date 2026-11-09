(function(){
  var q=document.getElementById('q');
  if(q){
    var cards=[].slice.call(document.querySelectorAll('.card[data-search]'));
    var none=document.getElementById('none');
    q.addEventListener('input',function(){
      var t=q.value.trim().toLowerCase(),shown=0;
      cards.forEach(function(c){
        var ok=!t||c.getAttribute('data-search').indexOf(t)>=0;
        c.hidden=!ok; if(ok)shown++;
        var hit=c.querySelector('.hit');
        var title=c.querySelector('.card-title').textContent.toLowerCase()+' '+c.querySelector('.eyebrow').textContent.toLowerCase();
        if(t&&ok&&title.indexOf(t)<0){hit.textContent='Contains an ingredient matching "'+q.value.trim()+'"';hit.hidden=false;}else{hit.hidden=true;}
      });
      none.hidden=shown>0;
    });
  }
  var sel=document.getElementById('shade');
  if(sel){sel.addEventListener('change',function(){
    [].forEach.call(document.querySelectorAll('.shade'),function(s){s.hidden=s.getAttribute('data-shade')!==sel.value;});
  });}
  [].forEach.call(document.querySelectorAll('.shade'),function(s){
    var btns=s.querySelectorAll('.fbtn[data-f]');
    [].forEach.call(btns,function(b){b.addEventListener('click',function(){
      [].forEach.call(btns,function(x){x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',x===b);});
      var f=b.getAttribute('data-f');
      [].forEach.call(s.querySelectorAll('.irow'),function(r){r.hidden=f!=='all'&&r.getAttribute('data-grp')!==f;});
    });});
  });
  var iq=document.getElementById('iq');
  if(iq){
    var rows=[].slice.call(document.querySelectorAll('.alist li')),rf='',inone=document.getElementById('inone');
    var apply=function(){var t=iq.value.trim().toLowerCase(),n=0;rows.forEach(function(r){
      var ok=(!t||r.getAttribute('data-search').indexOf(t)>=0)&&(!rf||r.getAttribute('data-r')===rf);r.hidden=!ok;if(ok)n++;});inone.hidden=n>0;};
    iq.addEventListener('input',apply);
    var fb=document.querySelectorAll('.fbtn[data-r]');
    [].forEach.call(fb,function(b){b.addEventListener('click',function(){rf=b.getAttribute('data-r');
      [].forEach.call(fb,function(x){x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',x===b);});apply();});});
  }
})();
