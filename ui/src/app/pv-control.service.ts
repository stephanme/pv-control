import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

export interface Meter {
  power_pv: number;
  power_consumption: number;
  power_grid: number;
}

export interface Wallbox {
  car_status?: number;
  max_current: number;
  allow_charging: boolean;
  phases_in: number;
  phases_out: number;
  power: number;
}

export enum ChargeMode {
  INIT = 'INIT',
  OFF_1P = 'OFF_1P',  // off = controller is off, wallbox may charge via app
  OFF_3P = 'OFF_3P',
  PV_ONLY = 'PV_ONLY',
  PV_ALL = 'PV_ALL',
}

export interface ChargerController {
  mode: ChargeMode;
  desired_mode: ChargeMode;
}

export interface PvControl {
  meter: Meter;
  wallbox: Wallbox;
  controller: ChargerController;
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

  public putPvControlDesiredChargeMode(mode: ChargeMode): Observable<void> {
    // Note: explicit json converion otherwise it is sent as plain text -> 400
    return this.http.put<void>('./api/pvcontrol/controller/desired_mode', JSON.stringify(mode), httpOptions);
  }
}
