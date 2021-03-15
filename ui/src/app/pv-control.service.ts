import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';


export interface PvControl {
  phases: number;
}

const httpOptions = {
  // eslint-disable-next-line @typescript-eslint/naming-convention
  headers: new HttpHeaders({ 'Content-Type': 'application/json' })
};

@Injectable({
  providedIn: 'root'
})
export class PvControlService {

  constructor(private http: HttpClient) { }

  public getPvControl(): Observable<PvControl> {
    return this.http.get<PvControl>('./api/pvcontrol');
  }

  public putPvControlPhases(phases: number): Observable<void> {
    return this.http.put<void>('./api/pvcontrol/phases', phases, httpOptions);
  }
}
