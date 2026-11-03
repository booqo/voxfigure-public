try{const s=localStorage.getItem('mc_theme');document.documentElement.dataset.theme=s||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark')}catch(e){}
