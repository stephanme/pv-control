import { ReactiveFormsModule } from '@angular/forms';
import { provideHttpClient, withInterceptors } from '@angular/common/http';

import { MatToolbar } from '@angular/material/toolbar';
import { MatCard, MatCardContent, MatCardHeader, MatCardTitle } from '@angular/material/card';
import { MatIcon } from '@angular/material/icon';
import { MatIconButton } from '@angular/material/button';
import { MatButtonToggle, MatButtonToggleGroup } from '@angular/material/button-toggle';

import { vi } from 'vitest';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { HarnessLoader } from '@angular/cdk/testing';
import { TestbedHarnessEnvironment } from '@angular/cdk/testing/testbed';
import { MatButtonHarness } from '@angular/material/button/testing';
import { MatButtonToggleHarness } from '@angular/material/button-toggle/testing';
import { MatSnackBarHarness } from '@angular/material/snack-bar/testing';

import { AppComponent } from './app.component';
import { ChargeMode, PhaseMode, Priority, PvControl } from './pv-control.service';
import { statusInterceptor } from './http-status.service';
import { provideZonelessChangeDetection } from '@angular/core';


describe('AppComponent', () => {
    let loader: HarnessLoader;
    let httpMock: HttpTestingController;
    let component: AppComponent;
    let fixture: ComponentFixture<AppComponent>;
    let pvControlData: PvControl;
    let chargeModeOff: MatButtonToggleHarness;
    let chargeModePvOnly: MatButtonToggleHarness;
    let chargeModeMax: MatButtonToggleHarness;
    let phaseModeAuto: MatButtonToggleHarness;
    let phaseModeCharge1P: MatButtonToggleHarness;
    let priorityAuto: MatButtonToggleHarness;
    let priorityCar: MatButtonToggleHarness;
    let refreshButton: MatButtonHarness;

    beforeEach(async () => {
        await TestBed.configureTestingModule({
            imports: [
                ReactiveFormsModule,
                MatCard,
                MatCardContent,
                MatCardHeader,
                MatCardTitle,
                MatIcon,
                MatIconButton,
                MatButtonToggle,
                MatButtonToggleGroup,
                MatToolbar,
                AppComponent
            ],
            providers: [
                provideZonelessChangeDetection(),
                provideHttpClient(withInterceptors([statusInterceptor])),
                provideHttpClientTesting(),
            ]
        }).compileComponents();

        fixture = TestBed.createComponent(AppComponent);
        loader = TestbedHarnessEnvironment.loader(fixture);
        component = fixture.componentInstance;
        httpMock = TestBed.inject(HttpTestingController);

        pvControlData = {
            meter: {
                error: 0,
                power_pv: 5000,
                power_consumption: 3000,
                power_grid: -1500,
                power_battery: -500,
                soc_battery: 50,
            },
            wallbox: {
                error: 0,
                car_status: 2,
                allow_charging: true,
                max_current: 8,
                phases_in: 3,
                phases_out: 3,
                power: 2000,
                temperature: 10.3,
            },
            controller: {
                error: 0,
                mode: ChargeMode.OFF,
                desired_mode: ChargeMode.OFF,
                phase_mode: PhaseMode.AUTO,
                priority: Priority.HOME_BATTERY,
                desired_priority: Priority.AUTO,
            },
            car: {
                error: 0,
                soc: 50,
                cruising_range: 150,
            }
        };

        vi.useFakeTimers();
        // wait for ngInit
        await fixture.whenStable();
        // pass initial 200ms wait for first refresh
        vi.advanceTimersByTime(300);

        chargeModeOff = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#chargeModeOFF' }));
        chargeModeMax = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#chargeModeMAX' }));
        chargeModePvOnly = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#chargeModePV_ONLY' }));
        phaseModeAuto = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#phaseModeAUTO' }));
        phaseModeCharge1P = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#phaseModeCHARGE_1P' }));
        priorityAuto = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#priorityAUTO' }));
        priorityCar = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#priorityCAR' }));
        refreshButton = await loader.getHarness(MatButtonHarness.with({ selector: '#refresh' }));
    });

    afterEach(() => {
        vi.useRealTimers();
        httpMock.verify();
    });

    it('should render the app', async () => {
        httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

        expect(component.chargeModeControl.value).toBe(ChargeMode.OFF);
        expect(await chargeModeOff.isChecked()).toBe(true);
        expect(component.phaseModeControl.value).toBe(PhaseMode.AUTO);
        expect(await phaseModeAuto.isChecked()).toBe(true);
        expect(component.priorityControl.value).toBe(Priority.AUTO);
        expect(await priorityAuto.isChecked()).toBe(true);

        expect(fixture.nativeElement.querySelector('#card-pv span').textContent).toContain('5.0 kW');
        expect(fixture.nativeElement.querySelector('#card-grid span').textContent).toContain('-1.5 kW');
        expect(fixture.nativeElement.querySelector('#card-grid mat-icon').className).toContain('col-green');
        expect(fixture.nativeElement.querySelector('#card-home span').textContent).toContain('1.0 kW');
        expect(fixture.nativeElement.querySelector('#card-battery span').textContent).toContain('-0.5 kW');
        expect(fixture.nativeElement.querySelector('#card-battery mat-icon').textContent).toContain('battery_charging_60');
        expect(fixture.nativeElement.querySelector('#card-car span').textContent).toContain('50 %');
        expect(fixture.nativeElement.querySelector('#card-temp span').textContent).toContain('10 °C');

        expect(fixture.nativeElement.querySelector('#car-max-current').textContent).toContain('3x 8 A');
        expect(fixture.nativeElement.querySelector('#car-charge-power').textContent).toContain('2.0 kW');
        expect(fixture.nativeElement.querySelector('#car-charge-state')).toBeNull();
    });

    it('should render car status', async () => {
        pvControlData.wallbox.car_status = 1;
        pvControlData.wallbox.phases_out = 0;
        httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

        expect(fixture.nativeElement.querySelector('#car-max-current')).toBeNull();
        expect(fixture.nativeElement.querySelector('#car-charge-power')).toBeNull();
        expect(fixture.nativeElement.querySelector('#car-charge-state').textContent).toContain('power_off');
    });

    it('should refresh data', async () => {
        const refreshIcon = fixture.nativeElement.querySelector('#refresh mat-icon');

        httpMock.expectOne('./api/pvcontrol').flush(pvControlData);
        vi.advanceTimersByTime(100);
        await fixture.whenStable();

        expect(refreshIcon.className).not.toContain('spin');
        expect(component.chargeModeControl.value).toBe(ChargeMode.OFF);

        pvControlData.controller.mode = ChargeMode.PV_ONLY;
        pvControlData.controller.desired_mode = ChargeMode.PV_ONLY;
        pvControlData.controller.phase_mode = PhaseMode.CHARGE_1P;
        pvControlData.controller.priority = Priority.CAR;
        pvControlData.controller.desired_priority = Priority.CAR;
        await refreshButton.click();
        vi.advanceTimersByTime(100);
        fixture.detectChanges();

        expect(refreshIcon.className).toContain('spin');
        httpMock.expectOne('./api/pvcontrol').flush(pvControlData);
        fixture.detectChanges();
        vi.advanceTimersByTime(100);
        await fixture.whenStable();

        expect(component.chargeModeControl.value).toBe(ChargeMode.PV_ONLY);
        expect(component.phaseModeControl.enabled).toBe(true);
        expect(component.phaseModeControl.value).toBe(PhaseMode.CHARGE_1P);
        expect(component.priorityControl.value).toBe(Priority.CAR);
        expect(await chargeModePvOnly.isChecked()).toBe(true);
        expect(await phaseModeCharge1P.isChecked()).toBe(true);
        expect(await priorityCar.isChecked()).toBe(true);
        expect(refreshIcon.className).not.toContain('spin');
    });

    it('should show an error msg on http problems', async () => {
        httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

        await refreshButton.click();
        httpMock.expectOne('./api/pvcontrol').flush('', {
            status: 500,
            statusText: 'Internal Server Error'
        });

        // snack bar is not below root element of fixture -> can't use loader
        const snackbar = await TestbedHarnessEnvironment.documentRootLoader(fixture).getHarness(MatSnackBarHarness);
        expect(await snackbar.getMessage()).toBe('HTTP 500 Internal Server Error - GET ./api/pvcontrol');
    });

    it('should show grey icons on sub system error', async () => {
        pvControlData.meter.error = 4;
        pvControlData.car.error = 4;
        pvControlData.wallbox.error = 4;
        httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

        vi.advanceTimersByTime(100);
        await fixture.whenStable();

        expect(fixture.nativeElement.querySelector('#card-pv mat-icon').className).toContain('col-grey');
        expect(fixture.nativeElement.querySelector('#card-pv span').className).toContain('col-grey');
        expect(fixture.nativeElement.querySelector('#card-grid mat-icon').className).toContain('col-grey');
        expect(fixture.nativeElement.querySelector('#card-grid span').className).toContain('col-grey');
        expect(fixture.nativeElement.querySelector('#card-home mat-icon').className).toContain('col-grey');
        expect(fixture.nativeElement.querySelector('#card-home span').className).toContain('col-grey');
        expect(fixture.nativeElement.querySelector('#card-battery span').className).toContain('col-grey');
        expect(fixture.nativeElement.querySelector('#card-battery mat-icon').className).toContain('col-grey');
        expect(fixture.nativeElement.querySelector('#card-car mat-icon').className).toContain('col-grey');
        expect(fixture.nativeElement.querySelector('#card-car span').className).toContain('col-grey');
        expect(fixture.nativeElement.querySelector('#card-chargemode mat-icon').className).toContain('col-grey');
        expect(fixture.nativeElement.querySelector('#card-chargemode span').className).toContain('col-grey');
        expect(fixture.nativeElement.querySelector('#card-temp mat-icon').className).toContain('col-grey');
        expect(fixture.nativeElement.querySelector('#card-temp span').className).toContain('col-grey');
    });

    it('should allow to switch to "PV only" charging', async () => {
        httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

        await chargeModePvOnly.check();

        const req = httpMock.expectOne('./api/pvcontrol/controller/desired_mode');
        expect(req.request.method).toBe('PUT');
        expect(req.request.body).toBe('"PV_ONLY"');
        req.flush(null);

        expect(await chargeModePvOnly.isChecked()).toBe(true);
        expect(await chargeModeOff.isChecked()).toBe(false);
    });

    it('should show Off in MANUAL mode', async () => {
        pvControlData.controller.desired_mode = ChargeMode.MANUAL;
        httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

        expect(await chargeModeOff.isChecked()).toBe(true);
    });

    it('should show Max in MANUAL mode', async () => {
        pvControlData.controller.desired_mode = ChargeMode.MANUAL;
        pvControlData.controller.mode = ChargeMode.MAX;
        httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

        expect(await chargeModeMax.isChecked()).toBe(true);
    });

    it('should allow to switch to "1 phase" charging', async () => {
        httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

        await phaseModeCharge1P.check();

        const req = httpMock.expectOne('./api/pvcontrol/controller/phase_mode');
        expect(req.request.method).toBe('PUT');
        expect(req.request.body).toBe('"CHARGE_1P"');
        req.flush(null);

        expect(await phaseModeCharge1P.isChecked()).toBe(true);
        expect(await phaseModeAuto.isChecked()).toBe(false);
    });

    it('should support disabled phase relay', async () => {
        pvControlData.controller.phase_mode = PhaseMode.DISABLED;
        httpMock.expectOne('./api/pvcontrol').flush(pvControlData);
        vi.advanceTimersByTime(100);
        await fixture.whenStable();

        expect(component.phaseModeControl.disabled).toBe(true);
        expect(await phaseModeAuto.isChecked()).toBe(false);
        expect(await phaseModeAuto.isDisabled()).toBe(true);
    });

    it('should allow to switch to charging priority CAR', async () => {
        httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

        await priorityCar.check();

        const req = httpMock.expectOne('./api/pvcontrol/controller/desired_priority');
        expect(req.request.method).toBe('PUT');
        expect(req.request.body).toBe('"CAR"');
        req.flush(null);

        expect(await priorityCar.isChecked()).toBe(true);
        expect(await priorityAuto.isChecked()).toBe(false);
    });
});

describe('AppComponent', () => {
    const pvControlData: PvControl = {
        meter: {
            error: 0,
            power_pv: 5000,
            power_consumption: 3000,
            power_grid: -1000,
            power_battery: -1000,
            soc_battery: 50,
        },
        wallbox: {
            error: 0,
            car_status: 1,
            allow_charging: false,
            max_current: 8,
            phases_in: 3,
            phases_out: 0,
            power: 0,
            temperature: 0,
        },
        controller: {
            error: 0,
            mode: ChargeMode.OFF,
            desired_mode: ChargeMode.OFF,
            phase_mode: PhaseMode.AUTO,
            priority: Priority.HOME_BATTERY,
            desired_priority: Priority.AUTO,
        },
        car: {
            error: 0,
            soc: 50,
            cruising_range: 150,
        }
    };

    it('should support wallboxChargingIcon()', () => {
        pvControlData.wallbox.phases_out = 0;
        pvControlData.wallbox.car_status = 0; // unknown
        expect(AppComponent.wallboxChargingIcon(pvControlData)).toBe('battery_unknown');

        pvControlData.wallbox.car_status = 1; // NoVehicle
        expect(AppComponent.wallboxChargingIcon(pvControlData)).toBe('power_off');
        pvControlData.wallbox.car_status = 2; // Charging
        expect(AppComponent.wallboxChargingIcon(pvControlData)).toBe('battery_charging_50');
        pvControlData.wallbox.car_status = 3; // WaitingForVehicle
        expect(AppComponent.wallboxChargingIcon(pvControlData)).toBe('hourglass_bottom');

        pvControlData.wallbox.car_status = 4; // ChargingFinished
        pvControlData.wallbox.allow_charging = false;
        expect(AppComponent.wallboxChargingIcon(pvControlData)).toBe('battery_3_bar');
        pvControlData.wallbox.allow_charging = true;
        expect(AppComponent.wallboxChargingIcon(pvControlData)).toBe('battery_full');
    });

    it('should support batteryIcon()', () => {
        pvControlData.meter.power_battery = -1000;
        pvControlData.meter.soc_battery = 0;
        expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_charging_20');
        pvControlData.meter.soc_battery = 50;
        expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_charging_60');
        pvControlData.meter.soc_battery = 99;
        expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_charging_full');
        pvControlData.meter.soc_battery = 100;
        expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_charging_full');

        pvControlData.meter.power_battery = 1000;
        pvControlData.meter.soc_battery = 0;
        expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_0_bar');
        pvControlData.meter.soc_battery = 50;
        expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_4_bar');
        pvControlData.meter.soc_battery = 90;
        expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_6_bar');
        pvControlData.meter.soc_battery = 99;
        expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_full');
        pvControlData.meter.soc_battery = 100;
        expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_full');

        pvControlData.meter.power_battery = 0;
        expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_full');
    });
});
