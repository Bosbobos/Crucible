export function Emblem({name='star'}:{name?:string}) {
 const paths:Record<string,string>={today:'M4 5h16v15H4z M8 3v4m8-4v4M4 10h16m-12 4h3m-3 3h6',
 practice:'M5 4h10l4 4v12H5z M14 4v5h5M8 13h8m-8 4h6',library:'M3 5c4-2 6-1 9 1 3-2 5-3 9-1v14c-4-2-6-1-9 1-3-2-5-3-9-1z M12 6v14',
 questions:'M4 4h16v13H9l-5 4z M8 8h8m-8 4h5',character:'M8 5l4-3 4 3-1 5-3 2-3-2z M7 13l5 2 5-2 3 7H4z',
 path:'M5 20V9l7-6 7 6v11M9 20v-6h6v6M3 9h18',collection:'M3 6h18M3 13h18M3 20h18M6 3v3m6-3v3m6-3v3M6 10v3m6-3v3m6-3v3',
 star:'M12 2l2 6 5-3-3 5 6 2-6 2 3 5-5-3-2 6-2-6-5 3 3-5-6-2 6-2-3-5 5 3z'};
 return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round" aria-hidden="true"><path d={paths[name]||paths.star}/></svg>;
}
