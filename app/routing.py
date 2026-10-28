"""Small orthogonal visibility router. Cards are obstacles, never shortcuts."""
import bisect
import heapq
import math


class Router:
    def __init__(self, positions, ports=()):
        self.boxes=[(p['x']-8,p['y']-8,p['x']+p['w']+8,p['y']+p['h']+8) for p in positions.values()]
        self.xs=sorted({x for a,_,b,_ in self.boxes for x in (a,b)}|{p[0] for p in ports})
        self.ys=sorted({y for _,a,_,b in self.boxes for y in (a,b)}|{p[1] for p in ports})
        self.valid={}
        self.steps=0
        self.failures=0

    def clear(self,a,b):
        if a==b:return True
        if abs(a[1]-b[1])<1e-7:
            lo,hi=sorted((a[0],b[0])); y=a[1]
            return not any(t+1e-7<y<d-1e-7 and lo<r-1e-7 and hi>l+1e-7 for l,t,r,d in self.boxes)
        if abs(a[0]-b[0])<1e-7:
            lo,hi=sorted((a[1],b[1])); x=a[0]
            return not any(l+1e-7<x<r-1e-7 and lo<d-1e-7 and hi>t+1e-7 for l,t,r,d in self.boxes)
        return False

    def free(self,p):
        return not any(l<p[0]<r and t<p[1]<b for l,t,r,b in self.boxes)

    def route(self,start,end,preferred=None):
        options=[preferred] if preferred and preferred[0]==start and preferred[-1]==end else []
        options += [[start,(start[0],end[1]),end],[start,(end[0],start[1]),end]]
        for points in options:
            if points and all(self.clear(a,b) for a,b in zip(points,points[1:])):
                return points
        # All ports/hubs are registered before routing; this graph is reused
        # across families. A bend penalty favours simple, readable lines.
        xs,ys=self.xs,self.ys
        source=(bisect.bisect_left(xs,start[0]),bisect.bisect_left(ys,start[1]))
        target=(bisect.bisect_left(xs,end[0]),bisect.bisect_left(ys,end[1]))
        queue=[(0.,0.,source[0],source[1],0)]; best={(source[0],source[1],0):0.}; previous={};final=None
        steps=0
        while queue and steps<12000 and self.steps<100000:
            steps+=1;self.steps+=1
            _,cost,x,y,direction=heapq.heappop(queue); node=(x,y,direction)
            if cost!=best.get(node):continue
            if (x,y)==target:final=node;break
            for nx,ny,nd in ((x-1,y,1),(x+1,y,1),(x,y-1,2),(x,y+1,2)):
                if not(0<=nx<len(xs) and 0<=ny<len(ys)):continue
                edge=tuple(sorted(((x,y),(nx,ny))))
                if edge not in self.valid:self.valid[edge]=self.clear((xs[x],ys[y]),(xs[nx],ys[ny]))
                if not self.valid[edge]:continue
                new=cost+abs(xs[x]-xs[nx])+abs(ys[y]-ys[ny])+(18 if direction and direction!=nd else 0)
                other=(nx,ny,nd)
                if new<best.get(other,math.inf):
                    best[other]=new;previous[other]=node
                    heuristic=abs(xs[nx]-end[0])+abs(ys[ny]-end[1])
                    heapq.heappush(queue,(new+heuristic,new,nx,ny,nd))
        if final is None:
            # Overlapping manually locked cards may obstruct a port itself.
            # Keep every relationship visible; the UI can recompose the view.
            self.failures+=1
            return options[-1]
        points=[];node=final
        while node in previous:
            points.append((xs[node[0]],ys[node[1]]));node=previous[node]
        return [start]+list(reversed(points))
