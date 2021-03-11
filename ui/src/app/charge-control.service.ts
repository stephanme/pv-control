import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';


export interface ChargeControl {
  phases: number;
}

const httpOptions = {
  // eslint-disable-next-line @typescript-eslint/naming-convention
  headers: new HttpHeaders({ 'Content-Type': 'application/json' })
};

@Injectable({
  providedIn: 'root'
})
export class ChargeControlService {

  constructor(private http: HttpClient) { }

  public getChargeControl(): Observable<ChargeControl> {
    return this.http.get<ChargeControl>('./api/chargecontrol');
  }

  public putChargeControlPhases(phases: number): Observable<void> {
    return this.http.put<void>('./api/chargecontrol/phases', phases, httpOptions);
  }
}
