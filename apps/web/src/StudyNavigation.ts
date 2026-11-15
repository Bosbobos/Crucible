import {createContext} from 'react';
export const StudyNavigation = createContext({material: (_id:string,_anchor?:string)=>{}, problem: (_id:string)=>{}, lab: ()=>{}});
