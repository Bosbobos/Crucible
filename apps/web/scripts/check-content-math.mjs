import {unified} from 'unified';
import remarkParse from 'remark-parse';
import remarkMath from 'remark-math';
import katex from 'katex';

let input='';for await(const chunk of process.stdin)input+=chunk;
const bundle=JSON.parse(input),parser=unified().use(remarkParse).use(remarkMath);
let count=0;const errors=[];
function markdown(text,source){
  function walk(node){
    if(node.type==='math'||node.type==='inlineMath'){
      count++;try{katex.renderToString(node.value,{throwOnError:true,trust:false,displayMode:node.type==='math'});}catch(error){errors.push({source,error:error.message});}
    }
    if(node.type==='code'&&node.lang==='vault-exercise')strings(JSON.parse(node.value),source);
    for(const child of node.children||[])walk(child);
  }
  walk(parser.parse(text));
}
function strings(value,source){if(typeof value==='string')markdown(value,source);else if(Array.isArray(value))value.forEach(item=>strings(item,source));else if(value&&typeof value==='object')Object.values(value).forEach(item=>strings(item,source));}
for(const card of bundle.problems)for(const field of ['statement','hints','solution','remember'])strings(card[field],card.id+'/'+field);
for(const topic of Object.values(bundle.topics))for(const field of ['core','theory'])if(topic[field])markdown(topic[field],topic.id+'/'+field);
console.log(JSON.stringify({formulas:count,errors},null,2));
if(errors.length)process.exitCode=1;
