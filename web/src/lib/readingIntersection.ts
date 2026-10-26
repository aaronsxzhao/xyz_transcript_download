/** Observer callbacks contain changes, not the entire set of visible headings. */
export function readingIntersection(onChange:(id:string)=>void):IntersectionObserverCallback {
  const visible=new Set<Element>()
  return entries=>{
    for(const entry of entries){
      if(entry.isIntersecting)visible.add(entry.target)
      else visible.delete(entry.target)
    }
    for(const element of visible)if(!element.isConnected)visible.delete(element)
    const first=[...visible].sort((a,b)=>a.getBoundingClientRect().top-b.getBoundingClientRect().top)[0]
    if(first)onChange(first.id)
  }
}
