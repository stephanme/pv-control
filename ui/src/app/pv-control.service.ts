import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

export interface Meter {
  power_pv: number;
  power_consumption: number;
  power_grid: number;
}

export interface Charger {
  phases: number;
  power_car: number;
  current_setpoint: number;
}

export interface PvControl {
  meter: Meter;
  charger: Charger;
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
    return this.http.put<void>('./api/pvcontrol/charger/phases', phases, httpOptions);
  }
}
