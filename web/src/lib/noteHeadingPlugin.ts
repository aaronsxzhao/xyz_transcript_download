import {uniqueNoteHeadingSlug} from './noteMarkdown'

type Node = {tagName?:string;value?:string;properties?:Record<string,unknown>;children?:Node[]}
/** Match Contents anchors in both the built-in reader and rich rendering. */
export function rehypeNoteHeadings({readerTitle}:{readerTitle?:string}={}) {
  return (tree:Node)=>{
    const counts:Record<string,number>=Object.create(null)
    const content=(node:Node):string=>node.value||node.children?.map(content).join('')||''
    const first=tree.children?.find(node=>node.tagName||node.value?.trim())
    const visit=(node:Node)=>{
      if(node.tagName&&/^h[1-6]$/.test(node.tagName)){
        node.properties={...node.properties,id:uniqueNoteHeadingSlug(content(node),counts)}
        if(node===first&&node.tagName==='h1'&&readerTitle&&content(node).trim()===readerTitle.trim()){
          node.tagName='span';node.children=[]
        }
      }
      node.children?.forEach(visit)
    }
    visit(tree)
  }
}
