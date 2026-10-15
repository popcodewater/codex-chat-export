import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

export async function markdownTokens(messages, moduleRoot) {
  const require = createRequire(path.join(moduleRoot, 'package.json'));
  const { Marked } = await import(pathToFileURL(require.resolve('marked')).href);
  const parser = new Marked({gfm:true,breaks:false,async:false});
  return messages.map(message => {
    // Host framing is hidden; literal tags inside fenced code remain intact.
    let fence = null, citation = false;
    const lines = message.text.split('\n').filter(line => {
      const match = line.match(/^\s*(`{3,}|~{3,})/);
      if (match) {
        if (!fence) fence = match[1];
        else if (match[1][0] === fence[0] && match[1].length >= fence.length) fence = null;
        return true;
      }
      if (fence) return true;
      if (line.includes('<oai-mem-citation>')) citation = true;
      if (citation) {if(line.includes('</oai-mem-citation>')) citation = false;return false;}
      return !/^\s*<\/?proposed_plan>\s*$/.test(line);
    });
    return {...message,tokens:parser.lexer(lines.join('\n'))};
  });
}

async function main() {
  const [input,output] = process.argv.slice(2);
  const data=JSON.parse(await fs.readFile(input,'utf8'));
  const messages=await markdownTokens(data.messages,process.env.CHAT_EXPORT_NODE_MODULES);
  await fs.writeFile(output,JSON.stringify({...data,messages}));
}
if(process.argv[1]&&pathToFileURL(path.resolve(process.argv[1])).href===import.meta.url){
  main().catch(error=>{console.error(`Markdown 解析失败：${error.message}`);process.exitCode=1;});
}
